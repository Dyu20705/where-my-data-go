"""
Deterministic Entity Resolution and Canonical Harmonization Engine.
Handles multi-pass identity matching, candidate fingerprint generation,
Source Authority Priority conflict resolution, and citation stub lifecycle.
"""

import json
from datetime import datetime, timezone
from typing import Dict, Any, Optional, Tuple, List
import duckdb

from ..models import (
    ParsedWork,
    ParsedAuthor,
    ParsedCitation,
    CanonicalWork,
    CanonicalAuthor,
    CanonicalVenue,
    CanonicalInstitution,
    CanonicalWorkProvenance,
    MetricsProvenance,
)
from ..identifiers import (
    mint_canonical_work_id,
    mint_canonical_author_id,
    mint_canonical_venue_id,
    mint_canonical_institution_id,
    compute_work_fingerprint,
    slugify_text,
    normalize_doi,
    normalize_arxiv_id,
    normalize_orcid,
    normalize_ror_id,
)


class MatchClassification:
    EXACT_MATCH = "EXACT_MATCH"
    PROBABLE_MATCH = "PROBABLE_MATCH"  # Candidate only, not auto-merged
    NO_MATCH = "NO_MATCH"


class EntityResolver:
    """Orchestrates multi-pass entity resolution and canonical relational updates."""

    # Priority matrix for attribute conflict resolution (Lower number = Higher authority)
    SOURCE_PRIORITIES = {
        "title": {
            "crossref": 1,
            "openalex": 2,
            "semantic_scholar": 3,
            "arxiv": 4,
        },
        "abstract": {
            "semantic_scholar": 1,
            "arxiv": 2,
            "openalex": 3,
            "crossref": 4,
        },
        "publication_date": {
            "crossref": 1,
            "openalex": 2,
            "semantic_scholar": 3,
            "arxiv": 4,
        },
        "venue": {
            "crossref": 1,
            "openalex": 2,
            "semantic_scholar": 3,
            "arxiv": 4,
        },
        "citation_count": {
            "semantic_scholar": 1,
            "openalex": 2,
            "crossref": 3,
            "arxiv": 4,
        },
    }

    def __init__(self, con: duckdb.DuckDBPyConnection):
        self.con = con

    def resolve_and_persist(
        self,
        work: ParsedWork,
        observation_id: str,
        run_id: str,
    ) -> str:
        """
        Resolves parsed work to canonical entity, resolves stubs or updates metadata,
        and atomically updates the Gold layer tables.
        Returns the resolved canonical_work_id.
        """
        # Step 1: Collect normalized candidate keys
        source_keys: List[Tuple[str, str, str]] = []  # (id_type, normalized_value, raw_value)
        if work.normalized_doi:
            source_keys.append(("DOI", work.normalized_doi, work.normalized_doi))
        if work.normalized_arxiv_id:
            source_keys.append(("ARXIV", work.normalized_arxiv_id, work.normalized_arxiv_id))
        for ext_type, ext_val in work.external_ids.items():
            clean_val = ext_val.strip()
            if clean_val and ext_type not in ("DOI", "ARXIV"):
                source_keys.append((ext_type.upper(), clean_val.lower(), clean_val))

        # Step 2: Resolve venue early
        venue_id = self._resolve_venue(work)

        # Step 3: Query existing canonical_work_identifiers for exact match
        existing_canonical_id, is_stub = self._lookup_canonical_id(source_keys)

        if existing_canonical_id:
            canonical_work_id = existing_canonical_id
            if is_stub:
                # Step 3a: Upgrade stub in-place
                self._upgrade_stub(canonical_work_id, work, observation_id, venue_id)
            else:
                # Step 3b: Existing canonical work -> apply Source Authority Priority Matrix
                self._update_existing_canonical(canonical_work_id, work, observation_id, venue_id)
        else:
            # Step 3c: Mint new canonical entity
            primary_key = self._select_primary_anchor(source_keys, work)
            canonical_work_id = mint_canonical_work_id(primary_key)
            self._insert_new_canonical(canonical_work_id, work, observation_id, venue_id)

        # Step 4: Register all source keys in canonical_work_identifiers
        self._register_identifiers(canonical_work_id, source_keys)

        # Step 5: Resolve and persist Authors & WorkAuthors
        self._resolve_authors(canonical_work_id, work.authors)

        # Step 6: Resolve and persist Citations (with Stub Provisioning)
        self._resolve_citations(canonical_work_id, work.citations, work.source_name)

        # Step 7: Record point-in-time metrics snapshot
        self._record_metrics(canonical_work_id, work, observation_id, run_id)

        return canonical_work_id

    def _lookup_canonical_id(
        self, source_keys: List[Tuple[str, str, str]]
    ) -> Tuple[Optional[str], bool]:
        """Looks up existing canonical work ID from source keys."""
        for id_type, norm_val, _ in source_keys:
            row = self.con.execute(
                """
                SELECT i.canonical_work_id, w.is_stub
                FROM canonical_work_identifiers i
                JOIN canonical_works w ON i.canonical_work_id = w.canonical_work_id
                WHERE i.identifier_type = ? AND i.normalized_value = ?
                LIMIT 1
                """,
                [id_type, norm_val],
            ).fetchone()
            if row:
                return row[0], bool(row[1])
        return None, False

    def _select_primary_anchor(
        self, source_keys: List[Tuple[str, str, str]], work: ParsedWork
    ) -> str:
        """Selects the primary anchor key for deterministic UUIDv5 minting."""
        for id_type, norm_val, _ in source_keys:
            if id_type == "DOI":
                return f"doi:{norm_val}"
        for id_type, norm_val, _ in source_keys:
            if id_type == "ARXIV":
                return f"arxiv:{norm_val}"
        for id_type, norm_val, _ in source_keys:
            return f"{id_type.lower()}:{norm_val}"
        # Fallback to source-scoped work id
        return f"cluster:{work.source_name}:{work.source_work_id}"

    def _insert_new_canonical(
        self,
        canonical_work_id: str,
        work: ParsedWork,
        observation_id: str,
        venue_id: Optional[str] = None,
    ) -> None:
        """Inserts a new canonical work record and records initial provenance."""
        now = datetime.now(timezone.utc)
        self.con.execute(
            """
            INSERT INTO canonical_works (
                canonical_work_id, title, abstract, publication_year, publication_date,
                canonical_doi, canonical_arxiv_id, canonical_venue_id, is_stub, citation_count,
                influential_citation_count, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, FALSE, ?, ?, ?, ?)
            """,
            [
                canonical_work_id,
                work.title,
                work.abstract,
                work.publication_year,
                work.publication_date,
                work.normalized_doi,
                work.normalized_arxiv_id,
                venue_id,
                work.citation_count,
                work.influential_citation_count,
                now,
                now,
            ],
        )
        # Record initial attribute provenance
        for attr in ("title", "abstract", "publication_date", "venue"):
            self.con.execute(
                """
                INSERT INTO canonical_work_provenance (
                    canonical_work_id, attribute_name, winning_source,
                    source_observation_id, resolution_rule, selected_at
                ) VALUES (?, ?, ?, ?, 'INITIAL_CREATION', ?)
                ON CONFLICT (canonical_work_id, attribute_name) DO UPDATE
                SET winning_source = EXCLUDED.winning_source,
                    source_observation_id = EXCLUDED.source_observation_id,
                    selected_at = EXCLUDED.selected_at
                """,
                [canonical_work_id, attr, work.source_name, observation_id, now],
            )

    def _upgrade_stub(
        self,
        canonical_work_id: str,
        work: ParsedWork,
        observation_id: str,
        venue_id: Optional[str] = None,
    ) -> None:
        """Upgrades a dangling citation stub into a full canonical work in-place."""
        now = datetime.now(timezone.utc)
        self.con.execute(
            """
            UPDATE canonical_works
            SET title = ?,
                abstract = COALESCE(?, abstract),
                publication_year = COALESCE(?, publication_year),
                publication_date = COALESCE(?, publication_date),
                canonical_doi = COALESCE(?, canonical_doi),
                canonical_arxiv_id = COALESCE(?, canonical_arxiv_id),
                canonical_venue_id = COALESCE(?, canonical_venue_id),
                is_stub = FALSE,
                stub_reason = NULL,
                citation_count = GREATEST(citation_count, ?),
                influential_citation_count = GREATEST(influential_citation_count, ?),
                updated_at = ?
            WHERE canonical_work_id = ?
            """,
            [
                work.title,
                work.abstract,
                work.publication_year,
                work.publication_date,
                work.normalized_doi,
                work.normalized_arxiv_id,
                venue_id,
                work.citation_count,
                work.influential_citation_count,
                now,
                canonical_work_id,
            ],
        )
        # Record provenance for the upgraded fields
        for attr in ("title", "abstract", "publication_date", "venue"):
            self.con.execute(
                """
                INSERT INTO canonical_work_provenance (
                    canonical_work_id, attribute_name, winning_source,
                    source_observation_id, resolution_rule, selected_at
                ) VALUES (?, ?, ?, ?, 'STUB_UPGRADE', ?)
                ON CONFLICT (canonical_work_id, attribute_name) DO UPDATE
                SET winning_source = EXCLUDED.winning_source,
                    source_observation_id = EXCLUDED.source_observation_id,
                    resolution_rule = 'STUB_UPGRADE',
                    selected_at = EXCLUDED.selected_at
                """,
                [canonical_work_id, attr, work.source_name, observation_id, now],
            )

    def _update_existing_canonical(
        self,
        canonical_work_id: str,
        work: ParsedWork,
        observation_id: str,
        venue_id: Optional[str] = None,
    ) -> None:
        """Evaluates source priorities and updates winning attributes."""
        now = datetime.now(timezone.utc)

        # Update Title if incoming source has higher priority
        if work.title:
            if self._should_update_attribute(canonical_work_id, "title", work.source_name):
                self.con.execute(
                    "UPDATE canonical_works SET title = ?, updated_at = ? WHERE canonical_work_id = ?",
                    [work.title, now, canonical_work_id],
                )
                self._set_provenance(canonical_work_id, "title", work.source_name, observation_id, "PRIORITY_OVERRIDE")

        # Update Abstract
        if work.abstract:
            if self._should_update_attribute(canonical_work_id, "abstract", work.source_name):
                self.con.execute(
                    "UPDATE canonical_works SET abstract = ?, updated_at = ? WHERE canonical_work_id = ?",
                    [work.abstract, now, canonical_work_id],
                )
                self._set_provenance(canonical_work_id, "abstract", work.source_name, observation_id, "PRIORITY_OVERRIDE")

        # Update Publication Date & Year
        if work.publication_year:
            if self._should_update_attribute(canonical_work_id, "publication_date", work.source_name):
                self.con.execute(
                    """
                    UPDATE canonical_works
                    SET publication_year = ?, publication_date = COALESCE(?, publication_date), updated_at = ?
                    WHERE canonical_work_id = ?
                    """,
                    [work.publication_year, work.publication_date, now, canonical_work_id],
                )
                self._set_provenance(canonical_work_id, "publication_date", work.source_name, observation_id, "PRIORITY_OVERRIDE")

        # Update Venue
        if venue_id:
            if self._should_update_attribute(canonical_work_id, "venue", work.source_name):
                self.con.execute(
                    "UPDATE canonical_works SET canonical_venue_id = ?, updated_at = ? WHERE canonical_work_id = ?",
                    [venue_id, now, canonical_work_id],
                )
                self._set_provenance(canonical_work_id, "venue", work.source_name, observation_id, "PRIORITY_OVERRIDE")

        # Update citation counts (keep max observed)
        if work.citation_count > 0 or work.influential_citation_count > 0:
            self.con.execute(
                """
                UPDATE canonical_works
                SET citation_count = GREATEST(citation_count, ?),
                    influential_citation_count = GREATEST(influential_citation_count, ?),
                    updated_at = ?
                WHERE canonical_work_id = ?
                """,
                [work.citation_count, work.influential_citation_count, now, canonical_work_id],
            )

    def _should_update_attribute(
        self, canonical_work_id: str, attribute: str, incoming_source: str
    ) -> bool:
        """Checks Source Authority Priority Matrix against current provenance."""
        current_prov = self.con.execute(
            """
            SELECT winning_source
            FROM canonical_work_provenance
            WHERE canonical_work_id = ? AND attribute_name = ?
            """,
            [canonical_work_id, attribute],
        ).fetchone()

        if not current_prov:
            return True

        incumbent_source = current_prov[0].lower()
        incoming = incoming_source.lower()

        priorities = self.SOURCE_PRIORITIES.get(attribute, {})
        incumbent_prio = priorities.get(incumbent_source, 99)
        incoming_prio = priorities.get(incoming, 99)

        return incoming_prio <= incumbent_prio

    def _set_provenance(
        self, canonical_work_id: str, attribute: str, source: str, observation_id: str, rule: str
    ) -> None:
        """Records attribute-level provenance pointing to source observation ID."""
        now = datetime.now(timezone.utc)
        self.con.execute(
            """
            INSERT INTO canonical_work_provenance (
                canonical_work_id, attribute_name, winning_source,
                source_observation_id, resolution_rule, selected_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT (canonical_work_id, attribute_name) DO UPDATE
            SET winning_source = EXCLUDED.winning_source,
                source_observation_id = EXCLUDED.source_observation_id,
                resolution_rule = EXCLUDED.resolution_rule,
                selected_at = EXCLUDED.selected_at
            """,
            [canonical_work_id, attribute, source, observation_id, rule, now],
        )

    def _register_identifiers(
        self, canonical_work_id: str, source_keys: List[Tuple[str, str, str]]
    ) -> None:
        """Inserts external identifier mappings into canonical_work_identifiers."""
        for id_type, norm_val, raw_val in source_keys:
            self.con.execute(
                """
                INSERT INTO canonical_work_identifiers (
                    identifier_type, normalized_value, canonical_work_id, raw_value
                ) VALUES (?, ?, ?, ?)
                ON CONFLICT (identifier_type, normalized_value) DO NOTHING
                """,
                [id_type, norm_val, canonical_work_id, raw_val],
            )

    def _resolve_venue(self, work: ParsedWork) -> Optional[str]:
        """Resolves or creates a canonical venue entity."""
        if not work.raw_venue_name:
            return None
        norm_name = slugify_text(work.raw_venue_name)
        if not norm_name:
            return None

        venue_id = mint_canonical_venue_id(norm_name, work.venue_issn)
        venue_type = work.venue_type or "UNSPECIFIED"

        self.con.execute(
            """
            INSERT INTO canonical_venues (
                canonical_venue_id, name, normalized_name, venue_type, tier, issn
            ) VALUES (?, ?, ?, ?, 'UNRANKED', ?)
            ON CONFLICT (canonical_venue_id) DO NOTHING
            """,
            [venue_id, work.raw_venue_name, norm_name, venue_type, work.venue_issn],
        )
        return venue_id

    def _resolve_authors(
        self, canonical_work_id: str, authors: List[ParsedAuthor]
    ) -> None:
        """Resolves or creates canonical authors and work_author junctions."""
        for author in authors:
            # Determine author anchor key
            if author.orcid:
                author_key = f"orcid:{author.orcid}"
            elif author.source_author_id:
                author_key = f"source_id:{author.source_author_id}"
            else:
                author_key = f"name:{slugify_text(author.raw_name)}"

            author_id = mint_canonical_author_id(author_key)

            # Upsert Author
            self.con.execute(
                """
                INSERT INTO canonical_authors (canonical_author_id, display_name, orcid)
                VALUES (?, ?, ?)
                ON CONFLICT (canonical_author_id) DO UPDATE
                SET orcid = COALESCE(canonical_authors.orcid, EXCLUDED.orcid)
                """,
                [author_id, author.raw_name, author.orcid],
            )

            # Resolve Institution if present
            inst_id = None
            if author.institution_name or author.institution_ror:
                inst_id = mint_canonical_institution_id(author.institution_ror, author.institution_name)
                self.con.execute(
                    """
                    INSERT INTO canonical_institutions (
                        canonical_inst_id, name, ror_id, country_code
                    ) VALUES (?, ?, ?, ?)
                    ON CONFLICT (canonical_inst_id) DO UPDATE
                    SET ror_id = COALESCE(canonical_institutions.ror_id, EXCLUDED.ror_id),
                        country_code = COALESCE(canonical_institutions.country_code, EXCLUDED.country_code)
                    """,
                    [
                        inst_id,
                        author.institution_name or "Unknown Institution",
                        author.institution_ror,
                        author.institution_country,
                    ],
                )

            # Insert WorkAuthor Junction
            self.con.execute(
                """
                INSERT INTO canonical_work_authors (
                    canonical_work_id, canonical_author_id, author_position,
                    canonical_inst_id, raw_author_name, raw_affiliation_string, is_corresponding
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (canonical_work_id, canonical_author_id, author_position) DO NOTHING
                """,
                [
                    canonical_work_id,
                    author_id,
                    author.position,
                    inst_id,
                    author.raw_name,
                    author.raw_affiliation,
                    author.is_corresponding,
                ],
            )

    def _resolve_citations(
        self,
        citing_work_id: str,
        citations: List[ParsedCitation],
        source_name: str,
    ) -> None:
        """Resolves target works for citation edges, auto-provisioning stubs if unindexed."""
        for cite in citations:
            target_work_id = None

            # Check if target work is identified by DOI
            if cite.cited_doi:
                row = self.con.execute(
                    "SELECT canonical_work_id FROM canonical_work_identifiers WHERE identifier_type = 'DOI' AND normalized_value = ?",
                    [cite.cited_doi],
                ).fetchone()
                if row:
                    target_work_id = row[0]
                else:
                    # Provision stub with target DOI
                    target_work_id = mint_canonical_work_id(f"doi:{cite.cited_doi}")
                    self._create_stub(
                        target_work_id,
                        title=f"[Stub Citation: {cite.cited_doi}]",
                        source_name=source_name,
                        identifiers=[("DOI", cite.cited_doi)],
                    )

            # Check if target work is identified by arXiv ID
            elif cite.cited_arxiv_id:
                row = self.con.execute(
                    "SELECT canonical_work_id FROM canonical_work_identifiers WHERE identifier_type = 'ARXIV' AND normalized_value = ?",
                    [cite.cited_arxiv_id],
                ).fetchone()
                if row:
                    target_work_id = row[0]
                else:
                    # Provision stub with target arXiv ID
                    target_work_id = mint_canonical_work_id(f"arxiv:{cite.cited_arxiv_id}")
                    self._create_stub(
                        target_work_id,
                        title=f"[Stub Citation: {cite.cited_arxiv_id}]",
                        source_name=source_name,
                        identifiers=[("ARXIV", cite.cited_arxiv_id)],
                    )

            # Check by target source work ID (e.g. OpenAlex or S2 paper ID)
            elif cite.cited_source_id:
                clean_src_id = cite.cited_source_id.strip().lower()
                row = self.con.execute(
                    "SELECT canonical_work_id FROM canonical_work_identifiers WHERE normalized_value = ?",
                    [clean_src_id],
                ).fetchone()
                if row:
                    target_work_id = row[0]
                else:
                    target_work_id = mint_canonical_work_id(f"cluster:{source_name}:{clean_src_id}")
                    id_type = "S2_PAPER_ID" if source_name == "semantic_scholar" else "OPENALEX"
                    self._create_stub(
                        target_work_id,
                        title=f"[Stub Citation: {clean_src_id}]",
                        source_name=source_name,
                        identifiers=[(id_type, clean_src_id)],
                    )

            if target_work_id and target_work_id != citing_work_id:
                self.con.execute(
                    """
                    INSERT INTO canonical_citations (
                        citing_work_id, cited_work_id, is_influential,
                        citation_intents, source_provider
                    ) VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT (citing_work_id, cited_work_id) DO UPDATE
                    SET is_influential = (canonical_citations.is_influential OR EXCLUDED.is_influential),
                        citation_intents = COALESCE(EXCLUDED.citation_intents, canonical_citations.citation_intents)
                    """,
                    [
                        citing_work_id,
                        target_work_id,
                        cite.is_influential,
                        cite.citation_intents,
                        source_name,
                    ],
                )

    def _create_stub(
        self,
        stub_id: str,
        title: str,
        source_name: str,
        identifiers: List[Tuple[str, str]],
    ) -> None:
        """Creates a lightweight stub work to preserve referential integrity for citation edges."""
        now = datetime.now(timezone.utc)
        doi = next((val for id_t, val in identifiers if id_t == "DOI"), None)
        arxiv_id = next((val for id_t, val in identifiers if id_t == "ARXIV"), None)

        self.con.execute(
            """
            INSERT INTO canonical_works (
                canonical_work_id, title, canonical_doi, canonical_arxiv_id,
                is_stub, stub_reason, created_from_source, created_at, updated_at
            ) VALUES (?, ?, ?, ?, TRUE, 'DANGLING_CITATION_TARGET', ?, ?, ?)
            ON CONFLICT (canonical_work_id) DO NOTHING
            """,
            [stub_id, title, doi, arxiv_id, source_name, now, now],
        )
        for id_type, val in identifiers:
            self.con.execute(
                """
                INSERT INTO canonical_work_identifiers (
                    identifier_type, normalized_value, canonical_work_id, raw_value
                ) VALUES (?, ?, ?, ?)
                ON CONFLICT (identifier_type, normalized_value) DO NOTHING
                """,
                [id_type, val, stub_id, val],
            )

    def _record_metrics(
        self,
        canonical_work_id: str,
        work: ParsedWork,
        observation_id: str,
        run_id: str,
    ) -> None:
        """Records append-only time-series metrics snapshots."""
        now = datetime.now(timezone.utc)
        if work.citation_count > 0:
            self.con.execute(
                """
                INSERT INTO metrics_provenance (
                    canonical_work_id, metric_name, metric_value,
                    source_provider, source_observation_id, run_id, observed_at
                ) VALUES (?, 'citation_count', ?, ?, ?, ?, ?)
                """,
                [
                    canonical_work_id,
                    float(work.citation_count),
                    work.source_name,
                    observation_id,
                    run_id,
                    now,
                ],
            )
        if work.influential_citation_count > 0:
            self.con.execute(
                """
                INSERT INTO metrics_provenance (
                    canonical_work_id, metric_name, metric_value,
                    source_provider, source_observation_id, run_id, observed_at
                ) VALUES (?, 'influential_citation_count', ?, ?, ?, ?, ?)
                """,
                [
                    canonical_work_id,
                    float(work.influential_citation_count),
                    work.source_name,
                    observation_id,
                    run_id,
                    now,
                ],
            )

"""
OpenAlex Metadata Parser.
Implements OpenAlex JSON work parsing including inverted index abstract reconstruction,
ROR institutional hierarchy mapping, and referenced work extraction.
"""

from datetime import datetime, date
import re
from typing import Dict, Any, Optional, List, Tuple
from .base import BaseSourceParser
from ..models import ParsedWork, ParsedAuthor, ParsedCitation
from ..identifiers import normalize_doi, normalize_orcid, normalize_ror_id


class OpenAlexParser(BaseSourceParser):
    """Parses OpenAlex Work JSON records."""

    source_name: str = "openalex"

    def parse_record(self, raw: Dict[str, Any]) -> ParsedWork:
        raw_id = str(raw.get("id") or "").strip()

        # Clean title
        title = self.clean_text(raw.get("title") or raw.get("display_name")) or ""

        # Abstract reconstruction from inverted index
        abstract = self.reconstruct_abstract(raw.get("abstract_inverted_index"))

        # Identifiers
        raw_doi = raw.get("doi")
        ids_dict = raw.get("ids") or {}
        if not raw_doi and "doi" in ids_dict:
            raw_doi = ids_dict["doi"]
        norm_doi = normalize_doi(raw_doi)

        # Dates
        pub_year = raw.get("publication_year")
        pub_date_str = raw.get("publication_date")
        pub_date = None
        if pub_date_str:
            try:
                pub_date = datetime.strptime(pub_date_str, "%Y-%m-%d").date()
                if not pub_year:
                    pub_year = pub_date.year
            except Exception:
                pass

        # Venue / Source
        primary_loc = raw.get("primary_location") or {}
        source_obj = primary_loc.get("source") or {}
        venue_name = source_obj.get("display_name")
        venue_issn = source_obj.get("issn_l")
        venue_type = source_obj.get("type", "UNSPECIFIED").upper()

        # Authorships
        authors = self._extract_authors(raw.get("authorships") or [])

        # Citations
        citations = self._extract_citations(raw.get("referenced_works") or [])

        # Citation Count
        cited_by_count = int(raw.get("cited_by_count") or 0)

        # External IDs Map
        external_ids: Dict[str, str] = {}
        if raw_id:
            external_ids["OPENALEX"] = raw_id
        if norm_doi:
            external_ids["DOI"] = norm_doi
        if "mag" in ids_dict:
            external_ids["MAG"] = str(ids_dict["mag"])
        if "pmid" in ids_dict:
            external_ids["PMID"] = str(ids_dict["pmid"])

        return ParsedWork(
            source_name=self.source_name,
            source_work_id=raw_id,
            title=title,
            abstract=abstract,
            publication_year=pub_year,
            publication_date=pub_date,
            normalized_doi=norm_doi,
            raw_venue_name=venue_name,
            venue_issn=venue_issn,
            venue_type=venue_type,
            citation_count=cited_by_count,
            influential_citation_count=0,
            authors=authors,
            citations=citations,
            external_ids=external_ids,
            raw_payload=raw,
        )

    @classmethod
    def reconstruct_abstract(cls, inverted_index: Optional[Dict[str, List[int]]]) -> Optional[str]:
        """
        Reconstructs human-readable text from an OpenAlex abstract inverted index.
        Inverted index structure: {'The': [0], 'model': [1, 5], ...}
        """
        if not inverted_index or not isinstance(inverted_index, dict):
            return None

        # Find maximum token position
        max_pos = -1
        for positions in inverted_index.values():
            if isinstance(positions, list) and positions:
                m = max(positions)
                if m > max_pos:
                    max_pos = m

        if max_pos < 0:
            return None

        # Construct token sequence
        tokens = [""] * (max_pos + 1)
        for word, positions in inverted_index.items():
            if isinstance(positions, list):
                for p in positions:
                    if 0 <= p <= max_pos:
                        tokens[p] = word

        reconstructed = " ".join(t for t in tokens if t)
        return cls.clean_text(reconstructed)

    def _extract_authors(self, authorships: List[Dict[str, Any]]) -> List[ParsedAuthor]:
        """Parses authors and institution hierarchies from authorships array."""
        authors: List[ParsedAuthor] = []
        for idx, ash in enumerate(authorships):
            author_obj = ash.get("author") or {}
            display_name = author_obj.get("display_name") or ash.get("raw_author_name") or ""
            author_id = author_obj.get("id")
            raw_orcid = author_obj.get("orcid")
            norm_orcid = normalize_orcid(raw_orcid)

            # Institution info
            institutions = ash.get("institutions") or []
            inst_name, inst_ror, inst_country = None, None, None
            if institutions and isinstance(institutions, list):
                first_inst = institutions[0]
                inst_name = first_inst.get("display_name")
                inst_ror = normalize_ror_id(first_inst.get("ror"))
                inst_country = first_inst.get("country_code")

            raw_affil = ash.get("raw_affiliation_string")

            if display_name:
                authors.append(
                    ParsedAuthor(
                        raw_name=display_name,
                        position=idx + 1,
                        orcid=norm_orcid,
                        source_author_id=author_id,
                        raw_affiliation=raw_affil or inst_name,
                        institution_name=inst_name,
                        institution_ror=inst_ror,
                        institution_country=inst_country,
                    )
                )
        return authors

    def _extract_citations(self, referenced_works: List[str]) -> List[ParsedCitation]:
        """Parses referenced works into citation objects."""
        citations: List[ParsedCitation] = []
        if isinstance(referenced_works, list):
            for ref in referenced_works:
                if isinstance(ref, str) and ref.strip():
                    citations.append(ParsedCitation(cited_source_id=ref.strip()))
        return citations

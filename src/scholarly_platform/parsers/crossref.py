"""
Crossref Metadata Parser.
Handles Crossref REST API JSON payloads, extracting Version of Record (VoR) publisher
metadata, official publication dates, container venues, and target reference DOIs.
"""

from datetime import date
import re
from typing import Dict, Any, Optional, List, Tuple
from .base import BaseSourceParser
from ..models import ParsedWork, ParsedAuthor, ParsedCitation
from ..identifiers import normalize_doi, normalize_orcid


class CrossrefParser(BaseSourceParser):
    """Parses Crossref Work JSON records."""

    source_name: str = "crossref"

    def parse_record(self, raw: Dict[str, Any]) -> ParsedWork:
        raw_doi = raw.get("DOI") or ""
        norm_doi = normalize_doi(raw_doi)

        # Title: Crossref stores title as an array of strings
        raw_titles = raw.get("title") or []
        title = ""
        if isinstance(raw_titles, list) and raw_titles:
            title = self.clean_text(raw_titles[0]) or ""
        elif isinstance(raw_titles, str):
            title = self.clean_text(raw_titles) or ""

        # Abstract: May be JATS XML (<jats:p>...</jats:p>)
        raw_abstract = raw.get("abstract") or ""
        clean_abstract = self._clean_jats(raw_abstract)

        # Dates & Year
        pub_date, pub_year = self._extract_date(raw)

        # Venue / Container
        container_titles = raw.get("container-title") or []
        venue_name = container_titles[0] if isinstance(container_titles, list) and container_titles else None
        issn_list = raw.get("ISSN") or []
        venue_issn = issn_list[0] if isinstance(issn_list, list) and issn_list else None

        # Authors
        authors = self._extract_authors(raw.get("author") or [])

        # Citations / References
        citations = self._extract_references(raw.get("reference") or [])

        # External IDs Map
        external_ids: Dict[str, str] = {}
        if norm_doi:
            external_ids["DOI"] = norm_doi

        return ParsedWork(
            source_name=self.source_name,
            source_work_id=raw_doi,
            title=title,
            abstract=clean_abstract,
            publication_year=pub_year,
            publication_date=pub_date,
            normalized_doi=norm_doi,
            raw_venue_name=venue_name,
            venue_issn=venue_issn,
            venue_type="JOURNAL" if "journal" in raw.get("type", "") else "CONFERENCE",
            citation_count=int(raw.get("is-referenced-by-count") or 0),
            influential_citation_count=0,
            authors=authors,
            citations=citations,
            external_ids=external_ids,
            raw_payload=raw,
        )

    def _clean_jats(self, text: str) -> Optional[str]:
        """Strips JATS XML tags and normalizes whitespace."""
        if not text:
            return None
        # Remove XML tags like <jats:p>, </jats:title>, etc.
        cleaned = re.sub(r"<[^>]+>", " ", text)
        return self.clean_text(cleaned)

    def _extract_date(self, raw: Dict[str, Any]) -> Tuple[Optional[date], Optional[int]]:
        """Extracts publication date from published-print, published-online, or issued date-parts."""
        for key in ("published-print", "published-online", "issued", "created"):
            val = raw.get(key)
            if isinstance(val, dict) and "date-parts" in val:
                parts_list = val["date-parts"]
                if isinstance(parts_list, list) and parts_list:
                    parts = parts_list[0]
                    if isinstance(parts, list) and parts:
                        year = parts[0]
                        month = parts[1] if len(parts) > 1 else 1
                        day = parts[2] if len(parts) > 2 else 1
                        try:
                            return date(year, month, day), year
                        except Exception:
                            return None, year
        return None, None

    def _extract_authors(self, authors_raw: List[Dict[str, Any]]) -> List[ParsedAuthor]:
        """Parses Crossref author entries."""
        authors: List[ParsedAuthor] = []
        if not isinstance(authors_raw, list):
            return authors

        for idx, a in enumerate(authors_raw):
            given = a.get("given", "").strip()
            family = a.get("family", "").strip()
            name = f"{given} {family}".strip() if given else family
            raw_orcid = a.get("ORCID")
            norm_orcid = normalize_orcid(raw_orcid)

            # Affiliations
            affil_list = a.get("affiliation") or []
            affil_name = None
            if affil_list and isinstance(affil_list, list):
                first = affil_list[0]
                if isinstance(first, dict):
                    affil_name = first.get("name")

            if name:
                authors.append(
                    ParsedAuthor(
                        raw_name=name,
                        position=idx + 1,
                        orcid=norm_orcid,
                        raw_affiliation=affil_name,
                    )
                )
        return authors

    def _extract_references(self, refs_raw: List[Dict[str, Any]]) -> List[ParsedCitation]:
        """Parses reference list items into citation references."""
        citations: List[ParsedCitation] = []
        if not isinstance(refs_raw, list):
            return citations

        for ref in refs_raw:
            ref_doi = ref.get("DOI")
            norm_ref_doi = normalize_doi(ref_doi) if ref_doi else None
            unstruct = ref.get("unstructured")
            if norm_ref_doi or unstruct:
                citations.append(
                    ParsedCitation(
                        cited_doi=norm_ref_doi,
                        raw_citation_string=unstruct,
                    )
                )
        return citations

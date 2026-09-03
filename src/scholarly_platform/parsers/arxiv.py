"""
arXiv Metadata Parser.
Handles arXiv OAI-PMH and bulk JSON records with LaTeX/TeX cleanup and author normalization.
"""

from datetime import datetime, date
import re
from typing import Dict, Any, Optional, List, Tuple
from .base import BaseSourceParser
from ..models import ParsedWork, ParsedAuthor, ParsedCitation
from ..identifiers import normalize_doi, normalize_arxiv_id


class ArxivParser(BaseSourceParser):
    """Parses arXiv metadata records."""

    source_name: str = "arxiv"

    def parse_record(self, raw: Dict[str, Any]) -> ParsedWork:
        # Extract arXiv identifier
        raw_id = str(raw.get("id") or "").strip()
        norm_arxiv = normalize_arxiv_id(raw_id, strip_version=True)

        # Title cleanup
        raw_title = raw.get("title") or ""
        clean_title = self.clean_tex(raw_title)

        # Abstract cleanup
        raw_abstract = raw.get("abstract") or raw.get("summary") or ""
        clean_abstract = self.clean_tex(raw_abstract)

        # DOI if previously published
        raw_doi = raw.get("doi")
        norm_doi = normalize_doi(raw_doi) if raw_doi else None

        # Publication date & year
        pub_date, pub_year = self._extract_date(raw)

        # Authors
        authors = self._extract_authors(raw)

        # Venue (journal-ref or arXiv category)
        journal_ref = raw.get("journal-ref") or raw.get("journal_ref")
        venue_name = journal_ref.strip() if journal_ref else "arXiv.org"

        # External IDs map
        external_ids: Dict[str, str] = {}
        if norm_arxiv:
            external_ids["ARXIV"] = norm_arxiv
        if norm_doi:
            external_ids["DOI"] = norm_doi

        # Citations are typically absent in raw arXiv records
        citations: List[ParsedCitation] = []

        return ParsedWork(
            source_name=self.source_name,
            source_work_id=raw_id or norm_arxiv or "unknown",
            title=clean_title,
            abstract=clean_abstract,
            publication_year=pub_year,
            publication_date=pub_date,
            normalized_doi=norm_doi,
            normalized_arxiv_id=norm_arxiv,
            raw_venue_name=venue_name,
            venue_type="PREPRINT_SERVER" if venue_name == "arXiv.org" else "JOURNAL",
            citation_count=0,
            influential_citation_count=0,
            authors=authors,
            citations=citations,
            external_ids=external_ids,
            raw_payload=raw,
        )

    def clean_tex(self, text: Optional[str]) -> str:
        """Removes excessive newlines, whitespace, and basic TeX escapes."""
        if not text:
            return ""
        cleaned = re.sub(r"\s+", " ", text).strip()
        # Clean basic TeX quotes
        cleaned = cleaned.replace("``", '"').replace("''", '"')
        cleaned = cleaned.replace("`", "'")
        return cleaned

    def _extract_date(self, raw: Dict[str, Any]) -> Tuple[Optional[date], Optional[int]]:
        """Extracts date and publication year from update_date, created, or versions."""
        date_str = raw.get("update_date") or raw.get("created")
        if not date_str and "versions" in raw and raw["versions"]:
            # Last version created date
            date_str = raw["versions"][-1].get("created")

        if date_str:
            # Handle formats: YYYY-MM-DD or RFC 2822
            try:
                # Try YYYY-MM-DD
                match = re.search(r"(\d{4})-(\d{2})-(\d{2})", str(date_str))
                if match:
                    y, m, d = int(match.group(1)), int(match.group(2)), int(match.group(3))
                    return date(y, m, d), y
            except Exception:
                pass

        # Fallback to year from modern arXiv ID (YYMM.NNNNN)
        raw_id = str(raw.get("id") or "")
        id_match = re.match(r"^(\d{2})(\d{2})\.\d+", raw_id)
        if id_match:
            yy = int(id_match.group(1))
            year = 2000 + yy if yy < 90 else 1900 + yy
            return date(year, 1, 1), year

        return None, None

    def _extract_authors(self, raw: Dict[str, Any]) -> List[ParsedAuthor]:
        """Parses authors from authors_parsed, authors string, or authors list."""
        authors: List[ParsedAuthor] = []
        pos = 1

        if "authors_parsed" in raw and isinstance(raw["authors_parsed"], list):
            for entry in raw["authors_parsed"]:
                if isinstance(entry, list) and len(entry) >= 2:
                    surname = (entry[0] or "").strip()
                    forename = (entry[1] or "").strip()
                    full_name = f"{forename} {surname}".strip() if forename else surname
                    affil = entry[2].strip() if len(entry) > 2 and entry[2] else None
                    if full_name:
                        authors.append(
                            ParsedAuthor(
                                raw_name=full_name,
                                position=pos,
                                raw_affiliation=affil,
                            )
                        )
                        pos += 1
        elif "authors" in raw:
            raw_authors = raw["authors"]
            if isinstance(raw_authors, str):
                # Split on comma or 'and'
                parts = re.split(r",\s*|\s+and\s+", raw_authors)
                for part in parts:
                    name = part.strip()
                    if name:
                        authors.append(ParsedAuthor(raw_name=name, position=pos))
                        pos += 1

        return authors

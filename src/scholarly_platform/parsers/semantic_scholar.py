"""
Semantic Scholar (S2AG) Metadata Parser.
Handles S2AG API and dataset JSON payloads, extracting contextual citations,
influential citation flags, citation intents, and cross-platform external IDs.
"""

from datetime import datetime, date
from typing import Dict, Any, Optional, List, Tuple
from .base import BaseSourceParser
from ..models import ParsedWork, ParsedAuthor, ParsedCitation
from ..identifiers import normalize_doi, normalize_arxiv_id


class SemanticScholarParser(BaseSourceParser):
    """Parses Semantic Scholar S2AG Work JSON records."""

    source_name: str = "semantic_scholar"

    def parse_record(self, raw: Dict[str, Any]) -> ParsedWork:
        paper_id = str(raw.get("paperId") or "").strip()
        corpus_id = raw.get("corpusId")

        # External IDs
        ext_ids = raw.get("externalIds") or {}
        raw_doi = ext_ids.get("DOI")
        norm_doi = normalize_doi(raw_doi)

        raw_arxiv = ext_ids.get("ArXiv")
        norm_arxiv = normalize_arxiv_id(raw_arxiv, strip_version=True)

        # Title & Abstract
        title = self.clean_text(raw.get("title")) or ""
        abstract = self.clean_text(raw.get("abstract"))

        # Dates & Year
        pub_date, pub_year = self._extract_date(raw)

        # Venue
        venue_obj = raw.get("publicationVenue") or {}
        venue_name = venue_obj.get("name") or raw.get("venue")
        venue_issn = venue_obj.get("issn")
        venue_type = venue_obj.get("type", "UNSPECIFIED").upper()

        # Authors
        authors = self._extract_authors(raw.get("authors") or [])

        # Contextual Citations
        citations = self._extract_citations(raw.get("citations") or [])

        # Metrics
        citation_count = int(raw.get("citationCount") or 0)
        influential_count = int(raw.get("influentialCitationCount") or 0)

        # External IDs Map
        external_ids_map: Dict[str, str] = {}
        if paper_id:
            external_ids_map["S2_PAPER_ID"] = paper_id
        if corpus_id:
            external_ids_map["CORPUS_ID"] = str(corpus_id)
        if norm_doi:
            external_ids_map["DOI"] = norm_doi
        if norm_arxiv:
            external_ids_map["ARXIV"] = norm_arxiv
        if "PubMed" in ext_ids:
            external_ids_map["PUBMED"] = str(ext_ids["PubMed"])
        if "DBLP" in ext_ids:
            external_ids_map["DBLP"] = str(ext_ids["DBLP"])

        return ParsedWork(
            source_name=self.source_name,
            source_work_id=paper_id or (str(corpus_id) if corpus_id else "unknown"),
            title=title,
            abstract=abstract,
            publication_year=pub_year,
            publication_date=pub_date,
            normalized_doi=norm_doi,
            normalized_arxiv_id=norm_arxiv,
            raw_venue_name=venue_name,
            venue_issn=venue_issn,
            venue_type=venue_type,
            citation_count=citation_count,
            influential_citation_count=influential_count,
            authors=authors,
            citations=citations,
            external_ids=external_ids_map,
            raw_payload=raw,
        )

    def _extract_date(self, raw: Dict[str, Any]) -> Tuple[Optional[date], Optional[int]]:
        """Extracts publication date and year."""
        pub_year = raw.get("year")
        date_str = raw.get("publicationDate")
        pub_date = None
        if date_str:
            try:
                pub_date = datetime.strptime(str(date_str), "%Y-%m-%d").date()
                if not pub_year:
                    pub_year = pub_date.year
            except Exception:
                pass
        return pub_date, pub_year

    def _extract_authors(self, authors_raw: List[Dict[str, Any]]) -> List[ParsedAuthor]:
        """Parses Semantic Scholar author records."""
        authors: List[ParsedAuthor] = []
        if not isinstance(authors_raw, list):
            return authors

        for idx, a in enumerate(authors_raw):
            name = (a.get("name") or "").strip()
            author_id = a.get("authorId")
            if name:
                authors.append(
                    ParsedAuthor(
                        raw_name=name,
                        position=idx + 1,
                        source_author_id=str(author_id) if author_id else None,
                    )
                )
        return authors

    def _extract_citations(self, citations_raw: List[Dict[str, Any]]) -> List[ParsedCitation]:
        """Extracts contextual citations annotated with intents and influential flags."""
        citations: List[ParsedCitation] = []
        if not isinstance(citations_raw, list):
            return citations

        for c in citations_raw:
            cited_id = c.get("paperId")
            is_inf = bool(c.get("isInfluential", False))
            intents = c.get("intents") or []
            if not isinstance(intents, list):
                intents = []
            clean_intents = [str(i).upper() for i in intents]

            if cited_id:
                citations.append(
                    ParsedCitation(
                        cited_source_id=str(cited_id).strip(),
                        is_influential=is_inf,
                        citation_intents=clean_intents,
                    )
                )
        return citations

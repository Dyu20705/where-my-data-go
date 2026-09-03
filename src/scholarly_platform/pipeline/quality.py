"""
Data Quality Assertion Framework.
Implements contracts DQ-01 to DQ-05 with strict severity and recovery actions:
- DQ-01: Identifier format & checksum validity (REJECT_ID)
- DQ-02: Title completeness and non-placeholder check (QUARANTINE)
- DQ-03: Publication year boundaries 1665..current_year+1 (SANITIZE)
- DQ-04: Citation graph edge validity, no self-loops (DROP_EDGE)
- DQ-05: Authorship sequence & non-empty name (SANITIZE)
"""

from datetime import datetime, timezone
from typing import Tuple, Optional, List
from ..models import ParsedWork, ParsedAuthor, ParsedCitation
from ..identifiers import normalize_doi, normalize_orcid, normalize_arxiv_id


class DataQualityResult:
    """Encapsulates the data quality evaluation of a parsed record."""

    def __init__(self, is_valid: bool = True):
        self.is_valid = is_valid
        self.quarantine_reason: Optional[str] = None
        self.error_type: Optional[str] = None
        self.warnings: List[str] = []

    def quarantine(self, error_type: str, reason: str) -> None:
        self.is_valid = False
        self.error_type = error_type
        self.quarantine_reason = reason

    def warn(self, warning: str) -> None:
        self.warnings.append(warning)


class DataQualityChecker:
    """Executes validation assertions over parsed scholarly works."""

    PLACEHOLDER_TITLES = {
        "[untitled]",
        "untitled",
        "none",
        "unknown",
        "n/a",
        "na",
        "null",
        "",
    }

    @classmethod
    def evaluate_work(cls, work: ParsedWork) -> Tuple[ParsedWork, DataQualityResult]:
        """
        Applies DQ-01 through DQ-05 rules to a ParsedWork.
        Returns the sanitized work and the quality assessment result.
        """
        result = DataQualityResult(is_valid=True)

        # ---------------------------------------------------------------------
        # DQ-02: Title Completeness (QUARANTINE)
        # ---------------------------------------------------------------------
        clean_title = (work.title or "").strip()
        if len(clean_title) < 3 or clean_title.lower() in cls.PLACEHOLDER_TITLES:
            result.quarantine(
                error_type="DQ-02_TITLE_INCOMPLETE",
                reason=f"Title '{work.title}' failed completeness check (length < 3 or placeholder).",
            )
            return work, result

        # ---------------------------------------------------------------------
        # DQ-01: Identifier Validity (REJECT_ID)
        # ---------------------------------------------------------------------
        if work.normalized_doi:
            valid_doi = normalize_doi(work.normalized_doi)
            if not valid_doi:
                result.warn(f"DQ-01: Rejected malformed DOI '{work.normalized_doi}'.")
                work.normalized_doi = None

        if work.normalized_arxiv_id:
            valid_arxiv = normalize_arxiv_id(work.normalized_arxiv_id)
            if not valid_arxiv:
                result.warn(f"DQ-01: Rejected malformed arXiv ID '{work.normalized_arxiv_id}'.")
                work.normalized_arxiv_id = None

        # ---------------------------------------------------------------------
        # DQ-03: Publication Year Boundaries (SANITIZE)
        # ---------------------------------------------------------------------
        current_year = datetime.now(timezone.utc).year
        if work.publication_year is not None:
            if not (1665 <= work.publication_year <= current_year + 1):
                result.warn(
                    f"DQ-03: Publication year {work.publication_year} out of bounds (1665..{current_year+1}). Sanitized to NULL."
                )
                work.publication_year = None

        # ---------------------------------------------------------------------
        # DQ-04: Citation Graph Edge Validity (DROP_EDGE)
        # ---------------------------------------------------------------------
        sanitized_citations: List[ParsedCitation] = []
        for cite in work.citations:
            # Check for self-citation by DOI
            if work.normalized_doi and cite.cited_doi and work.normalized_doi == cite.cited_doi:
                result.warn(f"DQ-04: Dropped self-citation edge to DOI {cite.cited_doi}.")
                continue
            # Check for self-citation by arXiv ID
            if work.normalized_arxiv_id and cite.cited_arxiv_id and work.normalized_arxiv_id == cite.cited_arxiv_id:
                result.warn(f"DQ-04: Dropped self-citation edge to arXiv {cite.cited_arxiv_id}.")
                continue
            # Check for self-citation by source_work_id
            if work.source_work_id and cite.cited_source_id and work.source_work_id == cite.cited_source_id:
                result.warn(f"DQ-04: Dropped self-citation edge to source ID {cite.cited_source_id}.")
                continue
            sanitized_citations.append(cite)
        work.citations = sanitized_citations

        # ---------------------------------------------------------------------
        # DQ-05: Authorship Sanity (SANITIZE)
        # ---------------------------------------------------------------------
        sanitized_authors: List[ParsedAuthor] = []
        pos = 1
        for author in work.authors:
            name = (author.raw_name or "").strip()
            if not name:
                result.warn("DQ-05: Discarded blank author name.")
                continue
            # Validate ORCID if present
            if author.orcid:
                valid_orcid = normalize_orcid(author.orcid)
                if not valid_orcid:
                    result.warn(f"DQ-01: Discarded invalid ORCID checksum '{author.orcid}'.")
                    author.orcid = None
                else:
                    author.orcid = valid_orcid

            author.raw_name = name
            author.position = pos
            sanitized_authors.append(author)
            pos += 1

        work.authors = sanitized_authors
        return work, result

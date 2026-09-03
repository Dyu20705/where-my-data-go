"""
Unit tests for Data Quality Assertion Framework (DQ-01 to DQ-05).
"""

from scholarly_platform.models import ParsedWork, ParsedAuthor, ParsedCitation
from scholarly_platform.pipeline.quality import DataQualityChecker


def test_dq02_quarantine_title():
    # Placeholder title triggers quarantine
    bad_work = ParsedWork(
        source_name="arxiv",
        source_work_id="123",
        title="[untitled]",
    )
    work, res = DataQualityChecker.evaluate_work(bad_work)
    assert not res.is_valid
    assert res.error_type == "DQ-02_TITLE_INCOMPLETE"

    short_work = ParsedWork(
        source_name="arxiv",
        source_work_id="124",
        title="ab",
    )
    work, res2 = DataQualityChecker.evaluate_work(short_work)
    assert not res2.is_valid
    assert res2.error_type == "DQ-02_TITLE_INCOMPLETE"


def test_dq01_reject_invalid_identifiers():
    work = ParsedWork(
        source_name="arxiv",
        source_work_id="125",
        title="Valid Paper Title",
        normalized_doi="invalid-doi-format",
        normalized_arxiv_id="invalid-arxiv",
        authors=[ParsedAuthor(raw_name="Jane Doe", position=1, orcid="0000-0002-1825-0099")],
    )
    sanitized, res = DataQualityChecker.evaluate_work(work)
    assert res.is_valid  # Still valid because record has valid title
    assert sanitized.normalized_doi is None  # Malformed DOI dropped
    assert sanitized.normalized_arxiv_id is None
    assert sanitized.authors[0].orcid is None  # Bad ORCID checksum dropped
    assert len(res.warnings) >= 3


def test_dq03_sanitize_publication_year():
    # Pre-1665
    work_old = ParsedWork(
        source_name="crossref",
        source_work_id="w1",
        title="Ancient Archimedes Treatise",
        publication_year=1200,
    )
    sanitized, res = DataQualityChecker.evaluate_work(work_old)
    assert res.is_valid
    assert sanitized.publication_year is None

    # Future year > now + 1
    work_future = ParsedWork(
        source_name="crossref",
        source_work_id="w2",
        title="Future SciFi Paper",
        publication_year=2099,
    )
    sanitized2, _ = DataQualityChecker.evaluate_work(work_future)
    assert sanitized2.publication_year is None


def test_dq04_drop_self_citation_edge():
    work = ParsedWork(
        source_name="openalex",
        source_work_id="W100",
        normalized_doi="10.1234/self",
        title="Paper with Self Citation",
        citations=[
            ParsedCitation(cited_doi="10.1234/self"),  # Self-citation
            ParsedCitation(cited_doi="10.1234/external"),
        ],
    )
    sanitized, res = DataQualityChecker.evaluate_work(work)
    assert res.is_valid
    assert len(sanitized.citations) == 1
    assert sanitized.citations[0].cited_doi == "10.1234/external"


def test_dq05_sanitize_authors():
    work = ParsedWork(
        source_name="arxiv",
        source_work_id="126",
        title="Valid Research Paper",
        authors=[
            ParsedAuthor(raw_name="", position=1),  # Blank name -> discard
            ParsedAuthor(raw_name="Valid Author", position=99),  # Fix position to 1
        ],
    )
    sanitized, res = DataQualityChecker.evaluate_work(work)
    assert res.is_valid
    assert len(sanitized.authors) == 1
    assert sanitized.authors[0].raw_name == "Valid Author"
    assert sanitized.authors[0].position == 1

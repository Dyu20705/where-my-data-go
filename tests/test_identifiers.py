"""
Unit tests for identifier normalization, fingerprinting, and UUIDv5 canonical minting.
"""

from scholarly_platform.identifiers import (
    normalize_doi,
    normalize_arxiv_id,
    normalize_orcid,
    normalize_ror_id,
    compute_payload_hash,
    compute_work_fingerprint,
    mint_canonical_work_id,
    mint_canonical_author_id,
    mint_canonical_venue_id,
    mint_canonical_institution_id,
)


def test_normalize_doi():
    # Valid DOIs
    assert normalize_doi("10.1145/3292500.3330964") == "10.1145/3292500.3330964"
    assert normalize_doi("https://doi.org/10.1145/3292500.3330964") == "10.1145/3292500.3330964"
    assert normalize_doi("http://dx.doi.org/10.1145/3292500.3330964") == "10.1145/3292500.3330964"
    assert normalize_doi("doi: 10.1038/nature12373") == "10.1038/nature12373"
    assert normalize_doi(" 10.48550/ARXIV.1706.03762 ") == "10.48550/arxiv.1706.03762"

    # Invalid DOIs
    assert normalize_doi("") is None
    assert normalize_doi("not-a-doi") is None
    assert normalize_doi(None) is None


def test_normalize_arxiv_id():
    # Modern format
    assert normalize_arxiv_id("1706.03762") == "1706.03762"
    assert normalize_arxiv_id("arXiv:1706.03762v5") == "1706.03762"
    assert normalize_arxiv_id("https://arxiv.org/abs/1706.03762v2") == "1706.03762"
    assert normalize_arxiv_id("1706.03762v5", strip_version=False) == "1706.03762v5"

    # Legacy format
    assert normalize_arxiv_id("hep-th/9901001") == "hep-th/9901001"
    assert normalize_arxiv_id("math.GT/0309136v1") == "math.gt/0309136"

    # Invalid
    assert normalize_arxiv_id("invalid-arxiv") is None
    assert normalize_arxiv_id("") is None


def test_normalize_orcid():
    # Valid ORCIDs with checksum validation (e.g. Josiah Carberry)
    assert normalize_orcid("0000-0002-1825-0097") == "0000-0002-1825-0097"
    assert normalize_orcid("https://orcid.org/0000-0002-1825-0097") == "0000-0002-1825-0097"
    assert normalize_orcid("0000000218250097") == "0000-0002-1825-0097"

    # Invalid checksum
    assert normalize_orcid("0000-0002-1825-0099") is None
    assert normalize_orcid("not-an-orcid") is None


def test_normalize_ror_id():
    assert normalize_ror_id("https://ror.org/03vek6s52") == "https://ror.org/03vek6s52"
    assert normalize_ror_id("03vek6s52") == "https://ror.org/03vek6s52"
    assert normalize_ror_id("invalid_ror") is None


def test_payload_hash():
    h1 = compute_payload_hash('{"title": "Paper A"}')
    h2 = compute_payload_hash('{"title": "Paper A"}')
    h3 = compute_payload_hash('{"title": "Paper B"}')
    assert h1 == h2
    assert h1 != h3
    assert len(h1) == 64


def test_work_fingerprint():
    fp1 = compute_work_fingerprint("Attention is All You Need", 2017, "Ashish Vaswani")
    fp2 = compute_work_fingerprint("Attention Is All You Need!", 2017, "Vaswani")
    # Title slugification removes punctuation and normalizes casing
    assert len(fp1) == 32
    assert isinstance(fp1, str)


def test_mint_canonical_work_id():
    # Same primary anchor key yields same UUIDv5
    id1 = mint_canonical_work_id("doi:10.1145/3292500.3330964")
    id2 = mint_canonical_work_id("doi:10.1145/3292500.3330964")
    id3 = mint_canonical_work_id("arxiv:1706.03762")
    assert id1 == id2
    assert id1 != id3
    assert len(id1) == 36

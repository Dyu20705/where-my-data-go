"""
Unit tests for arXiv, OpenAlex, Crossref, and Semantic Scholar parsers.
"""

from scholarly_platform.parsers.arxiv import ArxivParser
from scholarly_platform.parsers.openalex import OpenAlexParser
from scholarly_platform.parsers.crossref import CrossrefParser
from scholarly_platform.parsers.semantic_scholar import SemanticScholarParser


def test_arxiv_parser():
    raw_arxiv = {
        "id": "1706.03762v5",
        "title": "Attention Is All You Need\n",
        "abstract": "  The dominant sequence transduction models are based on complex recurrent or\nconvolutional neural networks. ",
        "authors_parsed": [
            ["Vaswani", "Ashish", "Google Brain"],
            ["Shazeer", "Noam", "Google Brain"],
        ],
        "doi": "10.48550/arXiv.1706.03762",
        "update_date": "2017-06-12",
        "journal-ref": "NeurIPS 2017",
    }
    parser = ArxivParser()
    parsed = parser.parse_record(raw_arxiv)

    assert parsed.source_name == "arxiv"
    assert parsed.normalized_arxiv_id == "1706.03762"
    assert parsed.normalized_doi == "10.48550/arxiv.1706.03762"
    assert parsed.title == "Attention Is All You Need"
    assert "recurrent or convolutional" in parsed.abstract
    assert parsed.publication_year == 2017
    assert len(parsed.authors) == 2
    assert parsed.authors[0].raw_name == "Ashish Vaswani"
    assert parsed.authors[0].raw_affiliation == "Google Brain"
    assert parsed.authors[0].position == 1
    assert parsed.raw_venue_name == "NeurIPS 2017"


def test_openalex_parser_inverted_index():
    raw_oa = {
        "id": "https://openalex.org/W2741809807",
        "doi": "https://doi.org/10.48550/arxiv.1706.03762",
        "title": "Attention Is All You Need",
        "abstract_inverted_index": {
            "The": [0],
            "Transformer": [1],
            "is": [2],
            "a": [3],
            "novel": [4],
            "architecture.": [5],
        },
        "publication_year": 2017,
        "publication_date": "2017-06-12",
        "primary_location": {
            "source": {
                "display_name": "Advances in Neural Information Processing Systems",
                "issn_l": "1060-1234",
                "type": "conference",
            }
        },
        "authorships": [
            {
                "author": {
                    "id": "https://openalex.org/A123",
                    "display_name": "Ashish Vaswani",
                    "orcid": "https://orcid.org/0000-0002-1825-0097",
                },
                "institutions": [
                    {
                        "display_name": "Google",
                        "ror": "https://ror.org/03vek6s52",
                        "country_code": "US",
                    }
                ],
            }
        ],
        "referenced_works": [
            "https://openalex.org/W111",
            "https://openalex.org/W222",
        ],
        "cited_by_count": 85000,
    }
    parser = OpenAlexParser()
    parsed = parser.parse_record(raw_oa)

    assert parsed.source_name == "openalex"
    assert parsed.normalized_doi == "10.48550/arxiv.1706.03762"
    assert parsed.abstract == "The Transformer is a novel architecture."
    assert parsed.citation_count == 85000
    assert len(parsed.authors) == 1
    assert parsed.authors[0].raw_name == "Ashish Vaswani"
    assert parsed.authors[0].orcid == "0000-0002-1825-0097"
    assert parsed.authors[0].institution_ror == "https://ror.org/03vek6s52"
    assert len(parsed.citations) == 2


def test_crossref_parser():
    raw_crossref = {
        "DOI": "10.1145/3292500.3330964",
        "title": ["A Benchmark for Scientific Trend Detection"],
        "abstract": "<jats:p>We introduce an empirical benchmark for trend discovery.</jats:p>",
        "published-print": {"date-parts": [[2019, 8, 4]]},
        "container-title": ["Proceedings of the 25th ACM SIGKDD"],
        "ISSN": ["1234-5678"],
        "type": "proceedings-article",
        "is-referenced-by-count": 42,
        "author": [
            {"given": "Jane", "family": "Doe", "ORCID": "http://orcid.org/0000-0002-1825-0097"}
        ],
        "reference": [
            {"DOI": "10.1145/12345.67890"},
            {"unstructured": "Vaswani et al. Attention Is All You Need. NeurIPS 2017."},
        ],
    }
    parser = CrossrefParser()
    parsed = parser.parse_record(raw_crossref)

    assert parsed.source_name == "crossref"
    assert parsed.normalized_doi == "10.1145/3292500.3330964"
    assert parsed.title == "A Benchmark for Scientific Trend Detection"
    assert parsed.abstract == "We introduce an empirical benchmark for trend discovery."
    assert parsed.publication_year == 2019
    assert parsed.citation_count == 42
    assert len(parsed.authors) == 1
    assert parsed.authors[0].raw_name == "Jane Doe"
    assert parsed.authors[0].orcid == "0000-0002-1825-0097"
    assert len(parsed.citations) == 2
    assert parsed.citations[0].cited_doi == "10.1145/12345.67890"


def test_semantic_scholar_parser():
    raw_s2 = {
        "paperId": "204e3073870fae3f05bcbc65e8a45f56662447e1",
        "corpusId": 1234567,
        "title": "Attention is All you Need",
        "abstract": "We propose a new simple network architecture, the Transformer...",
        "year": 2017,
        "publicationDate": "2017-06-12",
        "venue": "NeurIPS",
        "externalIds": {
            "DOI": "10.48550/arXiv.1706.03762",
            "ArXiv": "1706.03762",
            "DBLP": "conf/nips/VaswaniSPUJGKP17",
        },
        "authors": [
            {"authorId": "1751025", "name": "Ashish Vaswani"},
            {"authorId": "2468135", "name": "Noam Shazeer"},
        ],
        "citations": [
            {
                "paperId": "target_paper_1",
                "isInfluential": True,
                "intents": ["methodology", "background"],
            },
            {
                "paperId": "target_paper_2",
                "isInfluential": False,
                "intents": ["background"],
            },
        ],
        "citationCount": 92000,
        "influentialCitationCount": 12500,
    }
    parser = SemanticScholarParser()
    parsed = parser.parse_record(raw_s2)

    assert parsed.source_name == "semantic_scholar"
    assert parsed.normalized_doi == "10.48550/arxiv.1706.03762"
    assert parsed.normalized_arxiv_id == "1706.03762"
    assert parsed.citation_count == 92000
    assert parsed.influential_citation_count == 12500
    assert len(parsed.citations) == 2
    assert parsed.citations[0].is_influential is True
    assert parsed.citations[0].citation_intents == ["METHODOLOGY", "BACKGROUND"]

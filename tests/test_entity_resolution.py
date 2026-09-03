"""
Integration tests for multi-source entity resolution and identifier cluster unification.
"""

from pathlib import Path
from scholarly_platform.db import DatabaseManager
from scholarly_platform.pipeline.ingestion import IngestionCoordinator


def test_multi_source_unification(db_manager: DatabaseManager):
    coord = IngestionCoordinator(db_manager)
    con = db_manager.connection
    fixtures_dir = Path(__file__).parent / "fixtures"

    # Ingest from all 4 sources
    coord.ingest_file(str(fixtures_dir / "sample_arxiv.jsonl"), "arxiv")
    coord.ingest_file(str(fixtures_dir / "sample_openalex.jsonl"), "openalex")
    coord.ingest_file(str(fixtures_dir / "sample_crossref.jsonl"), "crossref")
    coord.ingest_file(str(fixtures_dir / "sample_semantic_scholar.jsonl"), "semantic_scholar")

    # Verify that the paper "Attention Is All You Need" (DOI: 10.48550/arxiv.1706.03762)
    # is resolved into exactly ONE canonical_work_id across all sources
    rows = con.execute(
        """
        SELECT canonical_work_id, COUNT(DISTINCT identifier_type) AS id_types, COUNT(*) AS total_ids
        FROM canonical_work_identifiers
        WHERE canonical_work_id IN (
            SELECT canonical_work_id FROM canonical_work_identifiers
            WHERE identifier_type = 'DOI' AND normalized_value = '10.48550/arxiv.1706.03762'
        )
        GROUP BY canonical_work_id
        """
    ).fetchall()

    assert len(rows) == 1  # Exactly ONE canonical entity!
    canonical_work_id, id_types, total_ids = rows[0]

    # Verify mapped identifier types
    id_list = con.execute(
        """
        SELECT identifier_type, normalized_value
        FROM canonical_work_identifiers
        WHERE canonical_work_id = ?
        ORDER BY identifier_type
        """,
        [canonical_work_id],
    ).fetchall()

    types_found = {row[0] for row in id_list}
    assert "DOI" in types_found
    assert "ARXIV" in types_found
    assert "OPENALEX" in types_found
    assert "S2_PAPER_ID" in types_found

    # Verify that canonical_works table only has ONE row for this paper
    work_rows = con.execute(
        "SELECT canonical_work_id, title, canonical_doi, canonical_arxiv_id FROM canonical_works WHERE canonical_work_id = ?",
        [canonical_work_id],
    ).fetchall()
    assert len(work_rows) == 1
    assert work_rows[0][2] == "10.48550/arxiv.1706.03762"
    assert work_rows[0][3] == "1706.03762"

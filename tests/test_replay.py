"""
Unit tests for idempotent replaying of identical input feeds.
"""

from pathlib import Path
from scholarly_platform.db import DatabaseManager
from scholarly_platform.pipeline.ingestion import IngestionCoordinator


def test_idempotent_replay(db_manager: DatabaseManager):
    coord = IngestionCoordinator(db_manager)
    con = db_manager.connection
    fixture_path = str(Path(__file__).parent / "fixtures" / "sample_arxiv.jsonl")

    # Run 1: Initial Ingestion
    run_1 = coord.ingest_file(fixture_path, "arxiv")
    assert run_1.accepted_count == 2

    works_count_1 = con.execute("SELECT COUNT(*) FROM canonical_works").fetchone()[0]
    idents_count_1 = con.execute("SELECT COUNT(*) FROM canonical_work_identifiers").fetchone()[0]
    assert works_count_1 == 2

    # Run 2: Replay Identical File
    run_2 = coord.ingest_file(fixture_path, "arxiv")
    assert run_2.record_count == 3
    assert run_2.accepted_count == 0  # Zero new records inserted because identical payload hashes were skipped!

    works_count_2 = con.execute("SELECT COUNT(*) FROM canonical_works").fetchone()[0]
    idents_count_2 = con.execute("SELECT COUNT(*) FROM canonical_work_identifiers").fetchone()[0]

    # Invariant: Canonical state is strictly unchanged
    assert works_count_2 == works_count_1
    assert idents_count_2 == idents_count_1

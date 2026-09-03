"""
Unit tests for run-level lineage tracking in ingestion_runs and Bronze quarantine.
"""

from pathlib import Path
from scholarly_platform.db import DatabaseManager
from scholarly_platform.pipeline.ingestion import IngestionCoordinator


def test_ingestion_run_lineage(db_manager: DatabaseManager):
    coord = IngestionCoordinator(db_manager)
    fixture_path = str(Path(__file__).parent / "fixtures" / "sample_arxiv.jsonl")

    run = coord.ingest_file(fixture_path, "arxiv")

    assert run.status == "COMPLETED"
    assert run.record_count == 3
    assert run.accepted_count == 2
    assert run.rejected_count == 1  # 1 untitled record quarantined
    assert len(run.input_hash) == 64

    # Verify DuckDB table records
    con = db_manager.connection
    run_row = con.execute("SELECT * FROM ingestion_runs WHERE run_id = ?", [run.run_id]).fetchone()
    assert run_row is not None
    assert run_row[1] == "arxiv"  # source_name
    assert run_row[4] == 3  # record_count
    assert run_row[5] == 2  # accepted_count
    assert run_row[6] == 1  # rejected_count
    assert run_row[13] == "COMPLETED"

    # Verify Quarantine Table
    quar_rows = con.execute("SELECT * FROM ingestion_quarantine WHERE run_id = ?", [run.run_id]).fetchall()
    assert len(quar_rows) == 1
    assert quar_rows[0][4] == "DQ-02_TITLE_INCOMPLETE"

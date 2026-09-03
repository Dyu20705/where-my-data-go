"""
Unit tests for transaction atomicity and failure rollback.
"""

from pathlib import Path
import pytest
from scholarly_platform.db import DatabaseManager
from scholarly_platform.pipeline.ingestion import IngestionCoordinator


def test_transaction_rollback_on_injected_failure(db_manager: DatabaseManager, monkeypatch):
    coord = IngestionCoordinator(db_manager)
    con = db_manager.connection
    fixture_path = str(Path(__file__).parent / "fixtures" / "sample_arxiv.jsonl")

    # Monkeypatch resolver to raise an injected exception during resolve_and_persist
    def mock_resolve_and_persist(*args, **kwargs):
        raise RuntimeError("Injected simulated worker failure during Gold resolution!")

    monkeypatch.setattr(
        "scholarly_platform.pipeline.resolver.EntityResolver.resolve_and_persist",
        mock_resolve_and_persist,
    )

    with pytest.raises(RuntimeError, match="Injected simulated worker failure"):
        coord.ingest_file(fixture_path, "arxiv")

    # Invariant: Entire transaction rolled back.
    # Zero records in ingestion_runs, raw_source_manifest, source_work_observations, or canonical_works!
    runs_count = con.execute("SELECT COUNT(*) FROM ingestion_runs").fetchone()[0]
    raw_count = con.execute("SELECT COUNT(*) FROM raw_source_manifest").fetchone()[0]
    obs_count = con.execute("SELECT COUNT(*) FROM source_work_observations").fetchone()[0]
    works_count = con.execute("SELECT COUNT(*) FROM canonical_works").fetchone()[0]

    assert runs_count == 0
    assert raw_count == 0
    assert obs_count == 0
    assert works_count == 0

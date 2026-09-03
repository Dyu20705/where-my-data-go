"""
Unit tests for attribute-level lineage, observation referencing, and metrics provenance.
"""

from pathlib import Path
from scholarly_platform.db import DatabaseManager
from scholarly_platform.pipeline.ingestion import IngestionCoordinator


def test_provenance_lineage_and_metrics(db_manager: DatabaseManager):
    coord = IngestionCoordinator(db_manager)
    con = db_manager.connection
    fixtures_dir = Path(__file__).parent / "fixtures"

    coord.ingest_file(str(fixtures_dir / "sample_arxiv.jsonl"), "arxiv")
    coord.ingest_file(str(fixtures_dir / "sample_openalex.jsonl"), "openalex")

    # Find canonical work for Attention Is All You Need
    canonical_id = con.execute(
        """
        SELECT canonical_work_id FROM canonical_work_identifiers
        WHERE identifier_type = 'DOI' AND normalized_value = '10.48550/arxiv.1706.03762'
        """
    ).fetchone()[0]

    # Verify canonical_work_provenance
    prov_rows = con.execute(
        """
        SELECT p.attribute_name, p.winning_source, p.source_observation_id, obs.source_work_id
        FROM canonical_work_provenance p
        JOIN source_work_observations obs ON p.source_observation_id = obs.observation_id
        WHERE p.canonical_work_id = ?
        """,
        [canonical_id],
    ).fetchall()

    attrs_found = {r[0] for r in prov_rows}
    assert "title" in attrs_found
    assert "abstract" in attrs_found
    assert "publication_date" in attrs_found
    assert "venue" in attrs_found

    # Verify that source_observation_id actually references valid rows in Silver
    for row in prov_rows:
        obs_id = row[2]
        obs_check = con.execute("SELECT COUNT(*) FROM source_work_observations WHERE observation_id = ?", [obs_id]).fetchone()[0]
        assert obs_check == 1

    # Verify metrics_provenance
    metrics_rows = con.execute(
        """
        SELECT metric_name, metric_value, source_provider, run_id
        FROM metrics_provenance
        WHERE canonical_work_id = ?
        ORDER BY observed_at
        """,
        [canonical_id],
    ).fetchall()

    assert len(metrics_rows) >= 1
    assert any(m[0] == "citation_count" for m in metrics_rows)

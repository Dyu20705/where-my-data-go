"""
Unit tests for technological trend mining analytical SQL queries.
"""

from pathlib import Path
from scholarly_platform.db import DatabaseManager
from scholarly_platform.pipeline.ingestion import IngestionCoordinator
from scholarly_platform.queries import ScholarlyAnalytics


def test_scholarly_analytics(db_manager: DatabaseManager):
    coord = IngestionCoordinator(db_manager)
    con = db_manager.connection
    fixtures_dir = Path(__file__).parent / "fixtures"

    coord.ingest_file(str(fixtures_dir / "sample_arxiv.jsonl"), "arxiv")
    coord.ingest_file(str(fixtures_dir / "sample_openalex.jsonl"), "openalex")
    coord.ingest_file(str(fixtures_dir / "sample_crossref.jsonl"), "crossref")
    coord.ingest_file(str(fixtures_dir / "sample_semantic_scholar.jsonl"), "semantic_scholar")

    # 1. Test Citation Velocity
    vel_results = ScholarlyAnalytics.citation_velocity(con, min_year=2015, limit=10)
    assert len(vel_results) > 0
    top_paper = vel_results[0]
    assert "title" in top_paper
    assert "citation_velocity" in top_paper
    assert top_paper["citation_velocity"] is not None
    assert top_paper["citation_count"] > 0

    # 2. Test Co-Authorship Network
    coauth_results = ScholarlyAnalytics.coauthorship_network(con, min_collaborations=1, limit=10)
    assert len(coauth_results) > 0
    edge = coauth_results[0]
    assert "author_1" in edge
    assert "author_2" in edge
    assert edge["shared_works"] >= 1

    # 3. Test Venue Impact
    venue_results = ScholarlyAnalytics.venue_impact(con, limit=10)
    assert len(venue_results) > 0
    venue_row = venue_results[0]
    assert "venue_name" in venue_row
    assert "total_works" in venue_row
    assert venue_row["total_works"] >= 1

    # 4. Test Provenance Audit Query
    prov_results = ScholarlyAnalytics.work_provenance_audit(con, top_paper["canonical_work_id"])
    assert len(prov_results) > 0
    assert any(p["attribute_name"] == "title" for p in prov_results)

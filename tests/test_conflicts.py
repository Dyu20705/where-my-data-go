"""
Unit tests for multi-source conflict resolution and Source Authority Priority Matrix.
"""

from scholarly_platform.db import DatabaseManager
from scholarly_platform.models import ParsedWork, ParsedAuthor
from scholarly_platform.pipeline.resolver import EntityResolver


def test_source_authority_conflict_resolution(db_manager: DatabaseManager):
    con = db_manager.connection
    resolver = EntityResolver(con)

    # Register initial dummy ingestion run
    con.execute("INSERT INTO ingestion_runs (run_id, source_name, input_hash) VALUES ('run_test', 'test', 'hash')")

    # Step 1: Ingest arXiv observation (Preprint authority)
    arxiv_work = ParsedWork(
        source_name="arxiv",
        source_work_id="1706.03762",
        normalized_doi="10.48550/arxiv.1706.03762",
        normalized_arxiv_id="1706.03762",
        title="Attention Is All You Need (arXiv preprint version)",
        abstract="arXiv abstract text...",
        publication_year=2017,
        raw_venue_name="arXiv.org",
        citation_count=1000,
    )
    # Record dummy Silver observation
    con.execute("""
        INSERT INTO source_work_observations (
            observation_id, run_id, source_name, source_work_id, title, observed_at
        ) VALUES ('obs_arxiv', 'run_test', 'arxiv', '1706.03762', 'Attention Is All You Need (arXiv preprint version)', CURRENT_TIMESTAMP)
    """)
    canonical_id_1 = resolver.resolve_and_persist(arxiv_work, "obs_arxiv", "run_test")

    # Verify initial state
    res_1 = con.execute("SELECT title FROM canonical_works WHERE canonical_work_id = ?", [canonical_id_1]).fetchone()
    assert res_1[0] == "Attention Is All You Need (arXiv preprint version)"

    prov_1 = con.execute(
        "SELECT winning_source, source_observation_id FROM canonical_work_provenance WHERE canonical_work_id = ? AND attribute_name = 'title'",
        [canonical_id_1],
    ).fetchone()
    assert prov_1[0] == "arxiv"
    assert prov_1[1] == "obs_arxiv"

    # Step 2: Ingest Crossref observation (Publisher Version of Record)
    # Crossref has HIGHER authority than arXiv for title (1 vs 4)
    crossref_work = ParsedWork(
        source_name="crossref",
        source_work_id="10.48550/arxiv.1706.03762",
        normalized_doi="10.48550/arxiv.1706.03762",
        title="Attention Is All You Need (Official Publisher VoR Title)",
        publication_year=2017,
        raw_venue_name="NeurIPS 2017",
        citation_count=1500,
    )
    con.execute("""
        INSERT INTO source_work_observations (
            observation_id, run_id, source_name, source_work_id, title, observed_at
        ) VALUES ('obs_crossref', 'run_test', 'crossref', '10.48550/arxiv.1706.03762', 'Attention Is All You Need (Official Publisher VoR Title)', CURRENT_TIMESTAMP)
    """)
    canonical_id_2 = resolver.resolve_and_persist(crossref_work, "obs_crossref", "run_test")

    # Must resolve to the EXACT SAME canonical work ID
    assert canonical_id_1 == canonical_id_2

    # Verify that Crossref won the title attribute over arXiv
    res_2 = con.execute("SELECT title FROM canonical_works WHERE canonical_work_id = ?", [canonical_id_1]).fetchone()
    assert res_2[0] == "Attention Is All You Need (Official Publisher VoR Title)"

    # Verify provenance was updated to point to Crossref observation
    prov_2 = con.execute(
        "SELECT winning_source, source_observation_id, resolution_rule FROM canonical_work_provenance WHERE canonical_work_id = ? AND attribute_name = 'title'",
        [canonical_id_1],
    ).fetchone()
    assert prov_2[0] == "crossref"
    assert prov_2[1] == "obs_crossref"
    assert prov_2[2] == "PRIORITY_OVERRIDE"

    # Step 3: Now feed an arXiv record with a different title.
    # Because arXiv priority (4) is LOWER than Crossref (1), Crossref's title must NOT be overwritten!
    arxiv_work_stale = ParsedWork(
        source_name="arxiv",
        source_work_id="1706.03762",
        normalized_doi="10.48550/arxiv.1706.03762",
        title="Attention Is All You Need (Late arriving lower authority title)",
    )
    resolver.resolve_and_persist(arxiv_work_stale, "obs_arxiv_2", "run_test")

    res_3 = con.execute("SELECT title FROM canonical_works WHERE canonical_work_id = ?", [canonical_id_1]).fetchone()
    # Still the Crossref title!
    assert res_3[0] == "Attention Is All You Need (Official Publisher VoR Title)"

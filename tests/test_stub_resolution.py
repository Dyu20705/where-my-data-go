"""
Unit tests for citation stub creation and seamless in-place stub-to-canonical upgrade.
"""

from scholarly_platform.db import DatabaseManager
from scholarly_platform.models import ParsedWork, ParsedCitation
from scholarly_platform.pipeline.resolver import EntityResolver


def test_stub_creation_and_upgrade_lifecycle(db_manager: DatabaseManager):
    con = db_manager.connection
    resolver = EntityResolver(con)

    con.execute("INSERT INTO ingestion_runs (run_id, source_name, input_hash) VALUES ('run_stub', 'test', 'hash')")

    # Step 1: Ingest Paper A, which cites an unindexed Paper B (DOI: 10.5555/seq2seq.2014)
    paper_a = ParsedWork(
        source_name="openalex",
        source_work_id="W_A",
        normalized_doi="10.1234/paper.a",
        title="Paper A: Large Scale Language Modeling",
        citations=[
            ParsedCitation(
                cited_doi="10.5555/seq2seq.2014",
                is_influential=True,
                citation_intents=["METHODOLOGY"],
            )
        ],
    )
    con.execute("""
        INSERT INTO source_work_observations (
            observation_id, run_id, source_name, source_work_id, title, observed_at
        ) VALUES ('obs_a', 'run_stub', 'openalex', 'W_A', 'Paper A: Large Scale Language Modeling', CURRENT_TIMESTAMP)
    """)
    canonical_id_a = resolver.resolve_and_persist(paper_a, "obs_a", "run_stub")

    # Verify that Paper A was created and is NOT a stub
    row_a = con.execute("SELECT is_stub FROM canonical_works WHERE canonical_work_id = ?", [canonical_id_a]).fetchone()
    assert row_a[0] is False

    # Verify that Paper B was automatically provisioned as a STUB
    stub_row = con.execute(
        """
        SELECT canonical_work_id, title, is_stub, stub_reason
        FROM canonical_works
        WHERE canonical_doi = '10.5555/seq2seq.2014'
        """
    ).fetchone()
    assert stub_row is not None
    stub_work_id = stub_row[0]
    assert stub_row[2] is True  # is_stub == TRUE
    assert stub_row[3] == "DANGLING_CITATION_TARGET"

    # Verify that citation edge exists in canonical_citations
    cite_edge = con.execute(
        """
        SELECT citing_work_id, cited_work_id, is_influential, citation_intents
        FROM canonical_citations
        WHERE citing_work_id = ? AND cited_work_id = ?
        """,
        [canonical_id_a, stub_work_id],
    ).fetchone()
    assert cite_edge is not None
    assert cite_edge[2] is True  # is_influential
    assert cite_edge[3] == ["METHODOLOGY"]

    # Step 2: Later, the actual metadata for Paper B arrives from Semantic Scholar
    paper_b_actual = ParsedWork(
        source_name="semantic_scholar",
        source_work_id="s2_b_real",
        normalized_doi="10.5555/seq2seq.2014",
        title="Sequence to Sequence Learning with Neural Networks",
        abstract="We present a general end-to-end approach to sequence learning...",
        publication_year=2014,
        raw_venue_name="NeurIPS 2014",
        citation_count=35000,
    )
    con.execute("""
        INSERT INTO source_work_observations (
            observation_id, run_id, source_name, source_work_id, title, observed_at
        ) VALUES ('obs_b', 'run_stub', 'semantic_scholar', 's2_b_real', 'Sequence to Sequence Learning with Neural Networks', CURRENT_TIMESTAMP)
    """)
    resolved_id_b = resolver.resolve_and_persist(paper_b_actual, "obs_b", "run_stub")

    # Invariant 1: The resolved ID MUST match the original stub_work_id!
    assert resolved_id_b == stub_work_id

    # Invariant 2: Stub must now be upgraded (is_stub == FALSE) and metadata fully populated
    upgraded_row = con.execute(
        """
        SELECT title, abstract, publication_year, is_stub, stub_reason
        FROM canonical_works
        WHERE canonical_work_id = ?
        """,
        [stub_work_id],
    ).fetchone()
    assert upgraded_row[0] == "Sequence to Sequence Learning with Neural Networks"
    assert "end-to-end approach" in upgraded_row[1]
    assert upgraded_row[2] == 2014
    assert upgraded_row[3] is False  # UPGRADED!
    assert upgraded_row[4] is None

    # Invariant 3: The inbound citation edge from Paper A is STILL intact!
    inbound_count = con.execute(
        "SELECT COUNT(*) FROM canonical_citations WHERE cited_work_id = ?",
        [stub_work_id],
    ).fetchone()[0]
    assert inbound_count == 1

    # Invariant 4: No duplicate works exist for this DOI
    doi_works_count = con.execute(
        "SELECT COUNT(*) FROM canonical_works WHERE canonical_doi = '10.5555/seq2seq.2014'"
    ).fetchone()[0]
    assert doi_works_count == 1

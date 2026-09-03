"""
Tests for versioned schema migrations, table creation, and constraint enforcement.
"""

import pytest
import duckdb
from scholarly_platform.db import DatabaseManager
from scholarly_platform.schema.migrations import MigrationManager


def test_schema_tables_exist(db_manager: DatabaseManager):
    """Verifies that all 13 Medallion tables and migration tracking exist."""
    con = db_manager.connection
    expected_tables = {
        "schema_migrations",
        # Bronze
        "ingestion_runs",
        "raw_source_manifest",
        "ingestion_quarantine",
        # Silver
        "source_work_observations",
        # Gold
        "canonical_venues",
        "canonical_institutions",
        "canonical_authors",
        "canonical_works",
        "canonical_work_identifiers",
        "canonical_work_authors",
        "canonical_citations",
        "canonical_work_provenance",
        "metrics_provenance",
        "canonical_work_aliases",
    }
    rows = con.execute("SHOW TABLES").fetchall()
    actual_tables = {r[0] for r in rows}
    assert expected_tables.issubset(actual_tables), f"Missing tables: {expected_tables - actual_tables}"


def test_migration_manager_idempotency(db_manager: DatabaseManager):
    """Verifies that applying migrations repeatedly is idempotent."""
    con = db_manager.connection
    mgr = MigrationManager(con)
    v1 = mgr.get_current_version()
    assert v1 == 1

    # Re-apply
    v2 = mgr.apply_all()
    assert v2 == 1


def test_primary_key_enforcement(db_manager: DatabaseManager):
    """Verifies that primary key duplicates are rejected by DuckDB."""
    con = db_manager.connection
    con.execute("""
        INSERT INTO ingestion_runs (run_id, source_name, input_hash)
        VALUES ('run-1', 'arxiv', 'hash-1');
    """)
    with pytest.raises(duckdb.ConstraintException):
        con.execute("""
            INSERT INTO ingestion_runs (run_id, source_name, input_hash)
            VALUES ('run-1', 'arxiv', 'hash-2');
        """)


def test_foreign_key_enforcement(db_manager: DatabaseManager):
    """Verifies that invalid foreign key references are rejected by DuckDB."""
    con = db_manager.connection
    with pytest.raises(duckdb.ConstraintException):
        con.execute("""
            INSERT INTO raw_source_manifest (raw_record_id, run_id, source_name, payload_hash, payload)
            VALUES ('rec-1', 'nonexistent-run', 'arxiv', 'h1', '{"test": 1}');
        """)

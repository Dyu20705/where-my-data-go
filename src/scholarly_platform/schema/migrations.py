"""
Versioned schema migration engine for DuckDB.
Ensures reproducible, idempotent DDL execution across all database instances.
"""

from typing import List, Tuple
import duckdb

# Migration 001: Initial Medallion Relational Schema
MIGRATION_001_DDL = """
-- Schema migration history tracking table
CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    description VARCHAR NOT NULL,
    applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================================
-- BRONZE LAYER: Ingestion Runs, Raw Manifest & Quarantine
-- ============================================================================

CREATE TABLE IF NOT EXISTS ingestion_runs (
    run_id VARCHAR PRIMARY KEY,
    source_name VARCHAR NOT NULL,
    input_uri VARCHAR,
    input_hash VARCHAR NOT NULL,
    record_count INTEGER DEFAULT 0,
    accepted_count INTEGER DEFAULT 0,
    rejected_count INTEGER DEFAULT 0,
    error_count INTEGER DEFAULT 0,
    pipeline_version VARCHAR DEFAULT '0.1.0',
    parser_version VARCHAR DEFAULT '0.1.0',
    schema_version VARCHAR DEFAULT '1.0.0',
    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP,
    status VARCHAR DEFAULT 'IN_PROGRESS'
);

CREATE TABLE IF NOT EXISTS raw_source_manifest (
    raw_record_id VARCHAR PRIMARY KEY,
    run_id VARCHAR NOT NULL REFERENCES ingestion_runs(run_id),
    source_name VARCHAR NOT NULL,
    source_record_id VARCHAR,
    payload_hash VARCHAR NOT NULL,
    payload JSON NOT NULL,
    ingested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS ingestion_quarantine (
    quarantine_id VARCHAR PRIMARY KEY,
    run_id VARCHAR NOT NULL REFERENCES ingestion_runs(run_id),
    source_name VARCHAR NOT NULL,
    raw_payload JSON NOT NULL,
    error_type VARCHAR NOT NULL,
    error_message VARCHAR NOT NULL,
    quarantined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================================
-- SILVER LAYER: Normalized Source Observations
-- ============================================================================

CREATE TABLE IF NOT EXISTS source_work_observations (
    observation_id VARCHAR PRIMARY KEY,
    run_id VARCHAR NOT NULL REFERENCES ingestion_runs(run_id),
    raw_record_id VARCHAR REFERENCES raw_source_manifest(raw_record_id),
    source_name VARCHAR NOT NULL,
    source_work_id VARCHAR NOT NULL,
    normalized_doi VARCHAR,
    normalized_arxiv_id VARCHAR,
    title VARCHAR,
    abstract VARCHAR,
    publication_date DATE,
    publication_year INTEGER,
    raw_venue_name VARCHAR,
    citation_count INTEGER,
    influential_citation_count INTEGER,
    raw_authors JSON,
    raw_citations JSON,
    observed_at TIMESTAMP NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================================
-- GOLD LAYER: Canonical Relational Domain Model
-- ============================================================================

CREATE TABLE IF NOT EXISTS canonical_venues (
    canonical_venue_id VARCHAR PRIMARY KEY,
    name VARCHAR NOT NULL,
    normalized_name VARCHAR NOT NULL,
    venue_type VARCHAR, -- 'CONFERENCE', 'JOURNAL', 'PREPRINT_SERVER'
    tier VARCHAR,       -- 'TIER_1', 'TIER_2', 'WORKSHOP', 'UNRANKED'
    issn VARCHAR,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS canonical_institutions (
    canonical_inst_id VARCHAR PRIMARY KEY,
    name VARCHAR NOT NULL,
    ror_id VARCHAR UNIQUE,
    country_code VARCHAR,
    homepage_url VARCHAR,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS canonical_authors (
    canonical_author_id VARCHAR PRIMARY KEY,
    display_name VARCHAR NOT NULL,
    orcid VARCHAR UNIQUE,
    aliases VARCHAR[],
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS canonical_works (
    canonical_work_id VARCHAR PRIMARY KEY,
    title VARCHAR NOT NULL,
    abstract VARCHAR,
    publication_year INTEGER,
    publication_date DATE,
    canonical_doi VARCHAR UNIQUE,
    canonical_arxiv_id VARCHAR UNIQUE,
    canonical_venue_id VARCHAR, -- Logical reference to canonical_venues(canonical_venue_id)
    is_stub BOOLEAN DEFAULT FALSE,
    stub_reason VARCHAR,        -- 'DANGLING_CITATION_TARGET', 'UNRESOLVED_REFERENCE'
    created_from_source VARCHAR,
    citation_count INTEGER DEFAULT 0,
    influential_citation_count INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Canonical Work Identifiers (Compound PK for Uniqueness & Cluster Resolution)
CREATE TABLE IF NOT EXISTS canonical_work_identifiers (
    identifier_type VARCHAR NOT NULL,   -- 'DOI', 'ARXIV', 'OPENALEX', 'S2_PAPER_ID', 'CORPUS_ID'
    normalized_value VARCHAR NOT NULL,  -- e.g. '10.1145/3292500.3330964'
    canonical_work_id VARCHAR NOT NULL, -- Logical reference to canonical_works(canonical_work_id)
    raw_value VARCHAR NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (identifier_type, normalized_value)
);

-- Canonical Work-Author Junction
CREATE TABLE IF NOT EXISTS canonical_work_authors (
    canonical_work_id VARCHAR NOT NULL, -- Logical reference to canonical_works(canonical_work_id)
    canonical_author_id VARCHAR NOT NULL, -- Logical reference to canonical_authors(canonical_author_id)
    author_position INTEGER NOT NULL,
    canonical_inst_id VARCHAR,          -- Logical reference to canonical_institutions(canonical_inst_id)
    raw_author_name VARCHAR,
    raw_affiliation_string VARCHAR,
    is_corresponding BOOLEAN DEFAULT FALSE,
    PRIMARY KEY (canonical_work_id, canonical_author_id, author_position)
);

-- Canonical Citation Graph (Directed Edges)
CREATE TABLE IF NOT EXISTS canonical_citations (
    citing_work_id VARCHAR NOT NULL, -- Logical reference to canonical_works(canonical_work_id)
    cited_work_id VARCHAR NOT NULL,  -- Logical reference to canonical_works(canonical_work_id)
    is_influential BOOLEAN DEFAULT FALSE,
    citation_intents VARCHAR[],      -- e.g. ['METHODOLOGY', 'BACKGROUND']
    source_provider VARCHAR NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (citing_work_id, cited_work_id)
);

-- Attribute-Level Lineage (References Source Observation ID)
CREATE TABLE IF NOT EXISTS canonical_work_provenance (
    canonical_work_id VARCHAR NOT NULL, -- Logical reference to canonical_works(canonical_work_id)
    attribute_name VARCHAR NOT NULL,    -- 'title', 'abstract', 'venue', 'publication_date'
    winning_source VARCHAR NOT NULL,
    source_observation_id VARCHAR NOT NULL REFERENCES source_work_observations(observation_id),
    resolution_rule VARCHAR NOT NULL,
    selected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (canonical_work_id, attribute_name)
);

-- Time-Series Metrics Snapshots
CREATE TABLE IF NOT EXISTS metrics_provenance (
    canonical_work_id VARCHAR NOT NULL, -- Logical reference to canonical_works(canonical_work_id)
    metric_name VARCHAR NOT NULL,       -- 'citation_count', 'influential_citation_count'
    metric_value DOUBLE NOT NULL,
    source_provider VARCHAR NOT NULL,
    source_observation_id VARCHAR REFERENCES source_work_observations(observation_id),
    run_id VARCHAR NOT NULL REFERENCES ingestion_runs(run_id),
    observed_at TIMESTAMP NOT NULL
);

-- Alias Resolution / Entity Merges
CREATE TABLE IF NOT EXISTS canonical_work_aliases (
    alias_work_id VARCHAR PRIMARY KEY,
    resolved_canonical_id VARCHAR NOT NULL, -- Logical reference to canonical_works(canonical_work_id)
    reason VARCHAR NOT NULL,
    merged_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

MIGRATIONS: List[Tuple[int, str, str]] = [
    (1, "Initial Medallion Relational Schema (Bronze, Silver, Gold)", MIGRATION_001_DDL),
]


class MigrationManager:
    """Applies versioned SQL migrations idempotently."""

    def __init__(self, connection: duckdb.DuckDBPyConnection):
        self.con = connection

    def get_current_version(self) -> int:
        """Returns the current migration version applied to the database."""
        try:
            res = self.con.execute(
                "SELECT COALESCE(MAX(version), 0) FROM schema_migrations"
            ).fetchone()
            return res[0] if res else 0
        except Exception:
            return 0

    def apply_all(self) -> int:
        """
        Applies all pending migrations in sequential order.
        Returns the new migration version.
        """
        # Ensure schema_migrations table exists
        self.con.execute("""
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version INTEGER PRIMARY KEY,
                description VARCHAR NOT NULL,
                applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        current_v = self.get_current_version()
        applied_count = 0

        for version, desc, ddl in MIGRATIONS:
            if version > current_v:
                # Execute DDL
                self.con.execute(ddl)
                # Record migration
                self.con.execute(
                    "INSERT INTO schema_migrations (version, description) VALUES (?, ?)",
                    [version, desc],
                )
                applied_count += 1

        return self.get_current_version()

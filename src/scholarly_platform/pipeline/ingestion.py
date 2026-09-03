"""
Ingestion Pipeline Coordinator.
Orchestrates Bronze raw landing & quarantine, Silver observation recording,
and Gold canonical entity resolution with atomic transaction management.
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, Optional, Generator, Tuple
import uuid
import duckdb

from ..db import DatabaseManager
from ..models import IngestionRun, ParsedWork
from ..identifiers import compute_payload_hash
from ..parsers.base import BaseSourceParser
from ..parsers.arxiv import ArxivParser
from ..parsers.openalex import OpenAlexParser
from ..parsers.crossref import CrossrefParser
from ..parsers.semantic_scholar import SemanticScholarParser
from .quality import DataQualityChecker
from .resolver import EntityResolver


class IngestionCoordinator:
    """Coordinates end-to-end multi-tier scholarly data ingestion."""

    PARSERS: Dict[str, BaseSourceParser] = {
        "arxiv": ArxivParser(),
        "openalex": OpenAlexParser(),
        "crossref": CrossrefParser(),
        "semantic_scholar": SemanticScholarParser(),
    }

    def __init__(self, db_manager: DatabaseManager):
        self.db = db_manager

    def ingest_file(
        self,
        file_path: str,
        source_name: str,
        run_id: Optional[str] = None,
    ) -> IngestionRun:
        """
        Ingests a raw JSONL file into DuckDB with atomic transaction guarantees.
        """
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"Input file not found: {file_path}")

        # Compute file hash
        file_bytes = path.read_bytes()
        input_hash = compute_payload_hash(file_bytes.decode("utf-8", errors="ignore"))

        active_run_id = run_id or f"run_{source_name}_{uuid.uuid4().hex[:12]}"
        now = datetime.now(timezone.utc)

        run = IngestionRun(
            run_id=active_run_id,
            source_name=source_name,
            input_uri=str(path.absolute()),
            input_hash=input_hash,
            started_at=now,
            status="IN_PROGRESS",
        )

        parser = self.PARSERS.get(source_name.lower())
        if not parser:
            raise ValueError(f"No parser available for source: {source_name}")

        with self.db.transaction() as con:
            # Register Ingestion Run in Bronze
            con.execute(
                """
                INSERT INTO ingestion_runs (
                    run_id, source_name, input_uri, input_hash,
                    pipeline_version, parser_version, schema_version,
                    started_at, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    run.run_id,
                    run.source_name,
                    run.input_uri,
                    run.input_hash,
                    run.pipeline_version,
                    run.parser_version,
                    run.schema_version,
                    run.started_at,
                    run.status,
                ],
            )

            resolver = EntityResolver(con)
            records_read = 0
            records_inserted = 0
            records_rejected = 0

            # Read lines
            lines = file_bytes.decode("utf-8", errors="ignore").splitlines()
            for line_idx, line in enumerate(lines):
                line_str = line.strip()
                if not line_str:
                    continue
                records_read += 1

                payload_hash = compute_payload_hash(line_str)
                try:
                    raw_dict = json.loads(line_str)
                except Exception as e:
                    # Malformed JSON -> Quarantine
                    records_rejected += 1
                    self._record_quarantine(
                        con,
                        run_id=run.run_id,
                        source_name=source_name,
                        raw_payload={"raw_line": line_str},
                        error_type="MALFORMED_JSON",
                        error_message=str(e),
                    )
                    continue

                # Check if identical payload already in raw_source_manifest (Idempotency)
                existing = con.execute(
                    "SELECT raw_record_id FROM raw_source_manifest WHERE payload_hash = ?",
                    [payload_hash],
                ).fetchone()
                if existing:
                    # Already ingested identical payload -> skip
                    continue

                # Parse record
                try:
                    parsed_work = parser.parse_record(raw_dict)
                except Exception as e:
                    records_rejected += 1
                    self._record_quarantine(
                        con,
                        run_id=run.run_id,
                        source_name=source_name,
                        raw_payload=raw_dict,
                        error_type="PARSER_EXCEPTION",
                        error_message=str(e),
                    )
                    continue

                # Data Quality Gates (DQ-01 to DQ-05)
                sanitized_work, dq_res = DataQualityChecker.evaluate_work(parsed_work)
                if not dq_res.is_valid:
                    records_rejected += 1
                    self._record_quarantine(
                        con,
                        run_id=run.run_id,
                        source_name=source_name,
                        raw_payload=raw_dict,
                        error_type=dq_res.error_type or "DQ_FAILURE",
                        error_message=dq_res.quarantine_reason or "DQ rule violation",
                    )
                    continue

                # Insert into Bronze raw_source_manifest
                raw_record_id = f"raw_{payload_hash[:16]}"
                con.execute(
                    """
                    INSERT INTO raw_source_manifest (
                        raw_record_id, run_id, source_name, source_record_id,
                        payload_hash, payload, ingested_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT (raw_record_id) DO NOTHING
                    """,
                    [
                        raw_record_id,
                        run.run_id,
                        source_name,
                        sanitized_work.source_work_id,
                        payload_hash,
                        json.dumps(raw_dict),
                        now,
                    ],
                )

                # Insert into Silver source_work_observations
                obs_id = f"obs_{run.run_id}_{line_idx}"
                con.execute(
                    """
                    INSERT INTO source_work_observations (
                        observation_id, run_id, raw_record_id, source_name,
                        source_work_id, normalized_doi, normalized_arxiv_id,
                        title, abstract, publication_date, publication_year,
                        raw_venue_name, citation_count, influential_citation_count,
                        raw_authors, raw_citations, observed_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    [
                        obs_id,
                        run.run_id,
                        raw_record_id,
                        source_name,
                        sanitized_work.source_work_id,
                        sanitized_work.normalized_doi,
                        sanitized_work.normalized_arxiv_id,
                        sanitized_work.title,
                        sanitized_work.abstract,
                        sanitized_work.publication_date,
                        sanitized_work.publication_year,
                        sanitized_work.raw_venue_name,
                        sanitized_work.citation_count,
                        sanitized_work.influential_citation_count,
                        json.dumps([a.__dict__ for a in sanitized_work.authors]),
                        json.dumps([c.__dict__ for c in sanitized_work.citations]),
                        now,
                    ],
                )

                # Resolve and persist to Gold layer
                resolver.resolve_and_persist(sanitized_work, obs_id, run.run_id)
                records_inserted += 1

            # Finalize Ingestion Run
            completed_now = datetime.now(timezone.utc)
            con.execute(
                """
                UPDATE ingestion_runs
                SET completed_at = ?,
                    status = 'COMPLETED',
                    record_count = ?,
                    accepted_count = ?,
                    rejected_count = ?
                WHERE run_id = ?
                """,
                [completed_now, records_read, records_inserted, records_rejected, run.run_id],
            )

            run.completed_at = completed_now
            run.status = "COMPLETED"
            run.record_count = records_read
            run.accepted_count = records_inserted
            run.rejected_count = records_rejected

        return run

    def _record_quarantine(
        self,
        con: duckdb.DuckDBPyConnection,
        run_id: str,
        source_name: str,
        raw_payload: Dict[str, Any],
        error_type: str,
        error_message: str,
    ) -> None:
        """Records a quarantined record in Bronze ingestion_quarantine."""
        quar_id = f"quar_{uuid.uuid4().hex[:16]}"
        now = datetime.now(timezone.utc)
        con.execute(
            """
            INSERT INTO ingestion_quarantine (
                quarantine_id, run_id, source_name, raw_payload,
                error_type, error_message, quarantined_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            [
                quar_id,
                run_id,
                source_name,
                json.dumps(raw_payload),
                error_type,
                error_message,
                now,
            ],
        )

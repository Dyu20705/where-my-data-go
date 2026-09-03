"""
Database Manager for Canonical Scholarly Data Platform.
Provides connection lifecycle management, transaction control, and versioned schema migrations.
"""

from contextlib import contextmanager
from pathlib import Path
from typing import Optional, Generator
import duckdb

from .schema.migrations import MigrationManager


class DatabaseManager:
    """Manages DuckDB database connections, schemas, and transactions."""

    def __init__(self, db_path: Optional[str] = None):
        """
        Initialize DatabaseManager.
        :param db_path: Path to .duckdb file or None for in-memory database.
        """
        self.db_path = db_path or ":memory:"
        self._connection: Optional[duckdb.DuckDBPyConnection] = None

    @property
    def connection(self) -> duckdb.DuckDBPyConnection:
        """Returns the active DuckDB connection, creating and migrating it if needed."""
        if self._connection is None:
            if self.db_path != ":memory:":
                parent = Path(self.db_path).parent
                parent.mkdir(parents=True, exist_ok=True)
            self._connection = duckdb.connect(self.db_path)
            self.init_schema()
        return self._connection

    def init_schema(self) -> int:
        """Initializes or migrates the schema using MigrationManager."""
        if self._connection is not None:
            mgr = MigrationManager(self._connection)
            return mgr.apply_all()
        return 0

    @contextmanager
    def transaction(self) -> Generator[duckdb.DuckDBPyConnection, None, None]:
        """Context manager providing an atomic transaction with automatic rollback on error."""
        con = self.connection
        con.execute("BEGIN TRANSACTION")
        try:
            yield con
            con.execute("COMMIT")
        except Exception:
            con.execute("ROLLBACK")
            raise

    def close(self) -> None:
        """Closes the active connection."""
        if self._connection is not None:
            self._connection.close()
            self._connection = None

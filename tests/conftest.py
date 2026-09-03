"""
Pytest configuration and fixtures for Canonical Scholarly Data Platform.
"""

import tempfile
from pathlib import Path
from typing import Generator
import pytest

from scholarly_platform.db import DatabaseManager


@pytest.fixture
def db_manager() -> Generator[DatabaseManager, None, None]:
    """Provides an in-memory DatabaseManager initialized with full Medallion schema."""
    mgr = DatabaseManager(":memory:")
    yield mgr
    mgr.close()


@pytest.fixture
def file_db_manager() -> Generator[DatabaseManager, None, None]:
    """Provides a file-based DatabaseManager in a temporary directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = str(Path(tmpdir) / "test_scholarly.duckdb")
        mgr = DatabaseManager(db_path)
        yield mgr
        mgr.close()

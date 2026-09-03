"""
Schema and migration management for DuckDB database.
"""

from .migrations import MigrationManager, MIGRATIONS

__all__ = ["MigrationManager", "MIGRATIONS"]

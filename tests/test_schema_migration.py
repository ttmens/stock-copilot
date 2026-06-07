"""Tests for schema migration module."""

import sqlite3
import tempfile
from pathlib import Path

import pytest

from src.data.schema_migration import (
    MIGRATIONS,
    get_current_version,
    get_migration_status,
    run_migrations,
)


class TestSchemaMigration:
    """Test schema migration system."""

    def test_migrations_list_not_empty(self):
        """MIGRATIONS should have at least one entry."""
        assert len(MIGRATIONS) >= 1

    def test_migrations_are_sequential(self):
        """Migration versions should be sequential starting from 1."""
        versions = [v for v, _, _ in MIGRATIONS]
        assert versions == list(range(1, len(MIGRATIONS) + 1))

    def test_run_migrations_creates_version_table(self):
        """run_migrations should create schema_version table."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            run_migrations(db_path)
            
            conn = sqlite3.connect(str(db_path))
            cursor = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='schema_version'"
            )
            assert cursor.fetchone() is not None
            conn.close()

    def test_run_migrations_applies_all(self):
        """run_migrations should apply all pending migrations."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            applied = run_migrations(db_path)
            
            assert applied == len(MIGRATIONS)
            
            # Verify version table has all entries
            conn = sqlite3.connect(str(db_path))
            cursor = conn.execute("SELECT COUNT(*) FROM schema_version")
            count = cursor.fetchone()[0]
            assert count == len(MIGRATIONS)
            conn.close()

    def test_run_migrations_idempotent(self):
        """Running migrations twice should not re-apply."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            
            first = run_migrations(db_path)
            second = run_migrations(db_path)
            
            assert first == len(MIGRATIONS)
            assert second == 0

    def test_get_current_version(self):
        """get_current_version should return latest applied version."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            
            # Before migrations
            conn = sqlite3.connect(str(db_path))
            assert get_current_version(conn) == 0
            conn.close()
            
            # After migrations
            run_migrations(db_path)
            conn = sqlite3.connect(str(db_path))
            assert get_current_version(conn) == len(MIGRATIONS)
            conn.close()

    def test_migration_2_creates_score_traces(self):
        """Migration 2 should create signal_score_traces table."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            run_migrations(db_path)
            
            conn = sqlite3.connect(str(db_path))
            cursor = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='signal_score_traces'"
            )
            assert cursor.fetchone() is not None
            conn.close()

    def test_migration_3_creates_health_table(self):
        """Migration 3 should create data_source_health table."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            run_migrations(db_path)
            
            conn = sqlite3.connect(str(db_path))
            cursor = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='data_source_health'"
            )
            assert cursor.fetchone() is not None
            conn.close()

    def test_get_migration_status(self):
        """get_migration_status should return correct counts."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            
            # Before migrations
            status = get_migration_status(db_path)
            assert status["current_version"] == 0
            assert status["pending_count"] == len(MIGRATIONS)
            
            # After migrations
            run_migrations(db_path)
            status = get_migration_status(db_path)
            assert status["current_version"] == len(MIGRATIONS)
            assert status["pending_count"] == 0

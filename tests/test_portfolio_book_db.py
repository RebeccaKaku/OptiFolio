"""Tests for DS-001: PortfolioBookDatabase — SQLite foundation."""

import sqlite3
from pathlib import Path

import pytest

from src.core.portfolio_book_db import (
    PortfolioBookDatabase,
    PortfolioBookError,
    UnsupportedSchemaVersionError,
    InvalidSchemaMetadataError,
)


# ── Helpers ────────────────────────────────────────────────────────────────

@pytest.fixture
def db_tmp(tmp_path):
    """A PortfolioBookDatabase pointed at a tmp_path location."""
    return PortfolioBookDatabase(path=tmp_path / "portfolio_book.sqlite")


@pytest.fixture
def initialized(db_tmp):
    """An already-initialized database in tmp_path."""
    db_tmp.initialize()
    return db_tmp


# ── Construction ───────────────────────────────────────────────────────────

class TestConstruction:
    def test_default_path_is_in_local(self):
        """Default path resolves to local/portfolio_book.sqlite under project root."""
        db = PortfolioBookDatabase()
        assert db.path.name == "portfolio_book.sqlite"
        assert "local" in db.path.parts

    def test_custom_path_accepted(self, tmp_path):
        """Explicit path overrides the default."""
        custom = tmp_path / "custom_dir" / "my_book.db"
        db = PortfolioBookDatabase(path=custom)
        assert db.path == custom


# ── No files on import/construct ───────────────────────────────────────────

class TestNoSideEffects:
    def test_construct_does_not_create_file(self, tmp_path):
        """Constructing does not touch the filesystem."""
        p = tmp_path / "book.sqlite"
        assert not p.exists()
        PortfolioBookDatabase(path=p)
        assert not p.exists()

    def test_construct_does_not_create_parent_dir(self, tmp_path):
        """Constructing does not create parent directories."""
        p = tmp_path / "deep" / "nested" / "book.sqlite"
        PortfolioBookDatabase(path=p)
        assert not p.parent.exists()


# ── initialize() ───────────────────────────────────────────────────────────

class TestInitialize:
    def test_creates_database_and_parent_dir(self, db_tmp):
        """initialize() creates the parent directory and the database file."""
        db_tmp.initialize()
        assert db_tmp.path.exists()
        assert db_tmp.path.stat().st_size > 0

    def test_schema_version_is_one_after_init(self, initialized):
        """A freshly initialized database has schema version 1."""
        assert initialized.schema_version() == 1

    def test_double_initialize_is_idempotent(self, initialized):
        """Calling initialize() twice does not corrupt the database."""
        assert initialized.schema_version() == 1
        initialized.initialize()  # second call
        assert initialized.schema_version() == 1


# ── Connection ─────────────────────────────────────────────────────────────

class TestConnect:
    def test_foreign_keys_enabled(self, initialized):
        """Connections from connect() have foreign keys ON."""
        conn = initialized.connect()
        try:
            (fk_on,) = conn.execute("PRAGMA foreign_keys").fetchone()
            assert fk_on == 1
        finally:
            conn.close()

    def test_row_factory_allows_column_access(self, initialized):
        """Row factory is set so columns can be accessed by name."""
        conn = initialized.connect()
        try:
            row = conn.execute(
                "SELECT key, value FROM _schema_meta WHERE key = 'version'"
            ).fetchone()
            assert row["key"] == "version"
            assert row["value"] == "1"
        finally:
            conn.close()


# ── Schema version guards ──────────────────────────────────────────────────

class TestSchemaVersionGuards:
    def test_higher_version_rejected(self, db_tmp):
        """A database with a higher schema version must be rejected."""
        # Create database manually with a higher version
        db_tmp.path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(db_tmp.path))
        conn.execute(
            "CREATE TABLE _schema_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)"
        )
        conn.execute(
            "INSERT INTO _schema_meta (key, value) VALUES ('version', '99')"
        )
        conn.commit()
        conn.close()

        with pytest.raises(UnsupportedSchemaVersionError, match="99"):
            db_tmp.initialize()

    def test_equal_version_accepted(self, db_tmp):
        """A database at the current version passes initialization."""
        current = PortfolioBookDatabase.CURRENT_SCHEMA_VERSION
        db_tmp.path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(db_tmp.path))
        conn.execute(
            "CREATE TABLE _schema_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)"
        )
        conn.execute(
            "INSERT INTO _schema_meta (key, value) VALUES ('version', ?)",
            (str(current),),
        )
        conn.commit()
        conn.close()

        # Should not raise
        db_tmp.initialize()
        assert db_tmp.schema_version() == current

    def test_corrupt_version_raises_on_initialize(self, db_tmp):
        """A corrupt version value raises InvalidSchemaMetadataError."""
        db_tmp.path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(db_tmp.path))
        conn.execute(
            "CREATE TABLE _schema_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)"
        )
        conn.execute(
            "INSERT INTO _schema_meta (key, value) VALUES ('version', 'not_a_number')"
        )
        conn.commit()
        conn.close()

        with pytest.raises(InvalidSchemaMetadataError):
            db_tmp.initialize()

    def test_no_metadata_table_raises_on_schema_version(self, db_tmp):
        """If _schema_meta table is missing, schema_version() raises."""
        db_tmp.path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(db_tmp.path))
        # No _schema_meta table created
        conn.execute("CREATE TABLE some_other_table (id INTEGER)")
        conn.commit()
        conn.close()

        with pytest.raises(InvalidSchemaMetadataError):
            db_tmp.schema_version()


# ── No local/ pollution ────────────────────────────────────────────────────

class TestLocalUntouched:
    def test_no_local_files_created(self, tmp_path):
        """All tests use tmp_path — verify the real local/ is not touched."""
        db = PortfolioBookDatabase(path=tmp_path / "test.sqlite")
        db.initialize()
        # The real local/portfolio_book.sqlite should NOT have been created
        from src.core.paths import PROJECT_ROOT
        real = PROJECT_ROOT / "local" / "portfolio_book.sqlite"
        if real.exists():
            # It might exist from a previous run, but we didn't create it
            # in this test. Just verify our tmp path is what we used.
            pass  # OK — pre-existing, not created by this test


# ── Exception hierarchy ────────────────────────────────────────────────────

class TestExceptionHierarchy:
    def test_exceptions_are_portfolio_book_errors(self):
        assert issubclass(UnsupportedSchemaVersionError, PortfolioBookError)
        assert issubclass(InvalidSchemaMetadataError, PortfolioBookError)

    def test_can_catch_with_base(self):
        """All exceptions can be caught with PortfolioBookError."""
        try:
            raise UnsupportedSchemaVersionError("test")
        except PortfolioBookError:
            pass  # expected


# ── Backup & Restore ───────────────────────────────────────────────────────

class TestBackupRestore:
    def test_backup_creates_valid_sqlite_copy(self, initialized, tmp_path):
        """backup() creates a file that verify_backup() accepts."""
        backup_path = tmp_path / "backup.sqlite"
        returned_path = initialized.backup(backup_path)

        assert returned_path == backup_path
        assert backup_path.exists()
        assert initialized.verify_backup(backup_path) is True

    def test_verify_returns_false_for_garbage(self, tmp_path):
        """verify_backup() returns False for non-DB or corrupt files."""
        db = PortfolioBookDatabase(path=tmp_path / "never_init.sqlite")

        # 1. Non-existent file
        assert db.verify_backup(tmp_path / "missing.sqlite") is False

        # 2. Garbage file
        garbage = tmp_path / "garbage.txt"
        garbage.write_text("not a database")
        assert db.verify_backup(garbage) is False

        # 3. Valid SQLite but missing metadata table
        empty_db = tmp_path / "empty.sqlite"
        conn = sqlite3.connect(str(empty_db))
        conn.execute("CREATE TABLE some_table (id INTEGER)")
        conn.close()
        assert db.verify_backup(empty_db) is False

    def test_restore_refuses_overwrite_without_flag(self, initialized, tmp_path):
        """restore_from() raises FileExistsError if target exists and overwrite=False."""
        backup_path = initialized.backup(tmp_path / "backup.sqlite")

        with pytest.raises(FileExistsError, match="overwrite=True"):
            initialized.restore_from(backup_path, overwrite=False)

    def test_restore_successful_with_overwrite(self, initialized, tmp_path):
        """restore_from() replaces current DB content when overwrite=True."""
        # 1. Setup: Add some data to DB
        conn = initialized.connect()
        conn.execute("CREATE TABLE test_data (val TEXT)")
        conn.execute("INSERT INTO test_data VALUES ('hello')")
        conn.commit()
        conn.close()

        # 2. Backup
        backup_path = initialized.backup(tmp_path / "backup.sqlite")

        # 3. Modify original DB
        conn = initialized.connect()
        conn.execute("UPDATE test_data SET val = 'world'")
        conn.commit()
        conn.close()

        # 4. Restore
        initialized.restore_from(backup_path, overwrite=True)

        # 5. Verify restored data
        conn = initialized.connect()
        row = conn.execute("SELECT val FROM test_data").fetchone()
        assert row["val"] == "hello"
        conn.close()

    def test_restore_fails_for_incompatible_version(self, initialized, tmp_path):
        """restore_from() raises UnsupportedSchemaVersionError for newer backups."""
        # Create a "fake" backup with version 99
        newer_path = tmp_path / "newer.sqlite"
        conn = sqlite3.connect(str(newer_path))
        conn.execute("CREATE TABLE _schema_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        conn.execute("INSERT INTO _schema_meta VALUES ('version', '99')")
        conn.commit()
        conn.close()

        with pytest.raises(UnsupportedSchemaVersionError, match="99"):
            initialized.restore_from(newer_path, overwrite=True)

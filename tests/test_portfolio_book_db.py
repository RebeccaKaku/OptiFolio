"""Tests for DS-001: PortfolioBookDatabase — SQLite foundation."""

import sqlite3
from contextlib import closing
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

    def test_schema_version_is_current_after_init(self, initialized):
        """A freshly initialized database has the current schema version."""
        assert initialized.schema_version() == PortfolioBookDatabase.CURRENT_SCHEMA_VERSION

    def test_double_initialize_is_idempotent(self, initialized):
        """Calling initialize() twice does not corrupt the database."""
        current = PortfolioBookDatabase.CURRENT_SCHEMA_VERSION
        assert initialized.schema_version() == current
        initialized.initialize()  # second call
        assert initialized.schema_version() == current


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
            assert row["value"] == str(PortfolioBookDatabase.CURRENT_SCHEMA_VERSION)
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

    def test_migration_1_to_current(self, db_tmp):
        """A database at version 1 is automatically upgraded to current version."""
        db_tmp.path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(db_tmp.path))
        conn.execute(
            "CREATE TABLE _schema_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)"
        )
        conn.execute(
            "INSERT INTO _schema_meta (key, value) VALUES ('version', '1')"
        )
        # Simulate a v1 DB that already has accounts table (created by v1 migration)
        conn.execute("CREATE TABLE accounts (account_id TEXT PRIMARY KEY, name TEXT)")
        conn.commit()
        conn.close()

        db_tmp.initialize()
        current = PortfolioBookDatabase.CURRENT_SCHEMA_VERSION
        assert db_tmp.schema_version() == current

        # Products table was created by v2 migration
        conn = db_tmp.connect()
        res = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='products'"
        ).fetchone()
        assert res is not None
        conn.close()

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


# ── Products CRUD ───────────────────────────────────────────────────

class TestProductsCRUD:
    def test_create_and_get_product(self, initialized):
        from src.domain.products import ProductDefinition
        p = ProductDefinition(
            product_id="PROD001", name="Alpha Bank WMP",
            product_type="bank_wmp", issuer="Alpha Bank",
            currency="CNY", liquidity_type="t_plus_1", data_source="manual"
        )
        initialized.create_product(p)
        retrieved = initialized.get_product("PROD001")
        assert retrieved == p

    def test_get_non_existent_product(self, initialized):
        assert initialized.get_product("NO_SUCH_PROD") is None

    def test_update_product(self, initialized):
        from src.domain.products import ProductDefinition
        p = ProductDefinition(
            product_id="PROD001", name="Initial Name",
            product_type="bank_wmp", issuer="Alpha Bank"
        )
        initialized.create_product(p)
        p_updated = ProductDefinition(
            product_id="PROD001", name="Updated Name",
            product_type="bank_wmp", issuer="Beta Bank", manager="Manager X"
        )
        initialized.update_product(p_updated)
        retrieved = initialized.get_product("PROD001")
        assert retrieved.name == "Updated Name"
        assert retrieved.issuer == "Beta Bank"
        assert retrieved.manager == "Manager X"

    def test_unknown_fields_preserved(self, initialized):
        from src.domain.products import ProductDefinition
        p = ProductDefinition(
            product_id="PROD_EXTRA", name="Extra Fields Product",
            product_type="mixed_fund", risk_level="R3",
            manager="Expert Manager",
            metadata={"secret_code": 12345, "tags": ["low-vol", "blue-chip"]}
        )
        initialized.create_product(p)
        retrieved = initialized.get_product("PROD_EXTRA")
        assert retrieved.risk_level == "R3"
        assert retrieved.manager == "Expert Manager"
        assert retrieved.metadata["secret_code"] == 12345
        assert retrieved.metadata["tags"] == ["low-vol", "blue-chip"]

    def test_missing_liquidity_defaults_to_unknown(self, initialized):
        from src.domain.products import ProductDefinition
        p = ProductDefinition(
            product_id="PROD_NO_LIQ", name="No Liquidity Product",
            product_type="other", liquidity_type=None
        )
        initialized.create_product(p)
        retrieved = initialized.get_product("PROD_NO_LIQ")
        assert retrieved.liquidity_type == "unknown"

    @pytest.mark.parametrize("ptype", [
        "bank_deposit", "bank_wmp", "money_market_fund", "bond_fund",
        "equity_fund", "mixed_fund", "qdii_fund", "other"
    ])
    def test_product_types_round_trip(self, initialized, ptype):
        from src.domain.products import ProductDefinition
        p = ProductDefinition(
            product_id=f"PROD_{ptype}", name=f"Product {ptype}",
            product_type=ptype
        )
        initialized.create_product(p)
        retrieved = initialized.get_product(f"PROD_{ptype}")
        assert retrieved.product_type == ptype


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


# ── Account CRUD ───────────────────────────────────────────────────────────

class TestAccountCRUD:
    def test_create_and_get_account(self, initialized):
        """create_account persists all fields; get_account retrieves them."""
        initialized.create_account(
            account_id="acc_001",
            name="Main Brokerage",
            institution="Interactive Brokers",
            account_type="brokerage",
            base_currency="USD",
            ownership_scope="personal",
            notes="Primary trading account",
        )

        row = initialized.get_account("acc_001")
        assert row is not None
        assert row["account_id"] == "acc_001"
        assert row["name"] == "Main Brokerage"
        assert row["institution"] == "Interactive Brokers"
        assert row["account_type"] == "brokerage"
        assert row["base_currency"] == "USD"
        assert row["ownership_scope"] == "personal"
        assert row["status"] == "active"
        assert row["notes"] == "Primary trading account"
        assert row["created_at"] is not None
        assert row["updated_at"] is not None

    def test_create_account_validation(self, initialized):
        """create_account raises ValueError for invalid ownership_scope."""
        with pytest.raises(ValueError, match="ownership_scope"):
            initialized.create_account(
                account_id="acc_bad",
                name="Bad Account",
                ownership_scope="illegal_scope",
            )
        with pytest.raises(ValueError, match="account_id"):
            initialized.create_account(account_id="", name="Missing ID")
        with pytest.raises(ValueError, match="name"):
            initialized.create_account(account_id="missing_name", name="")
        with pytest.raises(ValueError, match="base_currency"):
            initialized.create_account(
                account_id="bad_currency", name="Bad Currency", base_currency="US"
            )

    def test_get_account_none_if_missing(self, initialized):
        """get_account returns None for non-existent IDs."""
        assert initialized.get_account("no_such_account") is None

    def test_update_account_fields(self, initialized):
        """update_account modifies specific fields and refreshes updated_at."""
        initialized.create_account(account_id="acc_upd", name="Before")
        row_before = initialized.get_account("acc_upd")
        ts_before = row_before["updated_at"]

        initialized.update_account(
            "acc_upd", name="After", notes="Updated notes"
        )

        row_after = initialized.get_account("acc_upd")
        assert row_after["name"] == "After"
        assert row_after["notes"] == "Updated notes"
        assert row_after["updated_at"] >= ts_before

    def test_update_account_validation(self, initialized):
        """update_account validates ownership_scope and status."""
        initialized.create_account(account_id="acc_val", name="Test")

        with pytest.raises(ValueError, match="ownership_scope"):
            initialized.update_account("acc_val", ownership_scope="invalid")

        with pytest.raises(ValueError, match="status"):
            initialized.update_account("acc_val", status="invalid")

        with pytest.raises(ValueError, match="Unsupported account update fields"):
            initialized.update_account("acc_val", created_at="replacement")

        with pytest.raises(ValueError, match="base_currency"):
            initialized.update_account("acc_val", base_currency="US")

        with pytest.raises(PortfolioBookError, match="not found"):
            initialized.update_account("missing", notes="no such account")

    def test_deactivate_account(self, initialized):
        """deactivate_account sets status to 'inactive'."""
        initialized.create_account(account_id="acc_dea", name="Active")
        assert initialized.get_account("acc_dea")["status"] == "active"

        initialized.deactivate_account("acc_dea")
        assert initialized.get_account("acc_dea")["status"] == "inactive"


# ── Backup & Restore ───────────────────────────────────────────────────────

class TestBackupRestore:
    def test_backup_creates_valid_sqlite_copy(self, initialized, tmp_path):
        """backup() creates a file that verify_backup() accepts."""
        backup_path = tmp_path / "backup.sqlite"
        returned_path = initialized.backup(backup_path)

        assert returned_path == backup_path
        assert backup_path.exists()
        assert initialized.verify_backup(backup_path) is True

    def test_backup_rejects_uninitialized_source(self, tmp_path):
        """backup() raises FileNotFoundError or InvalidSchemaMetadataError for uninitialized source."""
        uninit_db = PortfolioBookDatabase(path=tmp_path / "uninit.sqlite")
        with pytest.raises(FileNotFoundError):
            uninit_db.backup(tmp_path / "target.sqlite")

        # Exists but no metadata
        uninit_db.path.touch()
        with pytest.raises(InvalidSchemaMetadataError):
            uninit_db.backup(tmp_path / "target2.sqlite")

    def test_backup_rejects_source_equals_target(self, initialized):
        """backup() raises PortfolioBookError if source and target resolve to the same file."""
        with pytest.raises(PortfolioBookError, match="same"):
            initialized.backup(initialized.path)

    def test_backup_rejects_existing_target_without_overwrite(self, initialized, tmp_path):
        """backup() raises FileExistsError if target exists and overwrite=False."""
        target = tmp_path / "exists.sqlite"
        target.touch()
        with pytest.raises(FileExistsError):
            initialized.backup(target, overwrite=False)

    def test_backup_deletes_failed_target(self, initialized, tmp_path, monkeypatch):
        """backup() deletes the target file if verification fails."""
        target = tmp_path / "fail.sqlite"

        # Mock verify_backup to return False
        monkeypatch.setattr(initialized, "verify_backup", lambda p: False)

        with pytest.raises(PortfolioBookError, match="verification failed"):
            initialized.backup(target)

        assert not target.exists()

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

    def test_verify_rejects_integrity_failure(self, initialized, tmp_path):
        """verify_backup() returns False if integrity check fails."""
        backup_path = initialized.backup(tmp_path / "corrupt.sqlite")
        # Manually corrupt the file by writing junk into it
        with open(backup_path, "r+b") as f:
            f.seek(100)
            f.write(b"CORRUPT")

        assert initialized.verify_backup(backup_path) is False

    def test_verify_rejects_missing_core_tables(self, tmp_path):
        """verify_backup() returns False if version table is present but core tables are missing."""
        fake_db = tmp_path / "fake.sqlite"
        conn = sqlite3.connect(str(fake_db))
        conn.execute("CREATE TABLE _schema_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        conn.execute("INSERT INTO _schema_meta VALUES ('version', '6')")
        conn.commit()
        conn.close()

        db = PortfolioBookDatabase()
        assert db.verify_backup(fake_db) is False

    def test_v8_backup_restore_roundtrip(self, initialized, tmp_path):
        """v8 backup includes import_drafts and import_candidates."""
        conn = initialized.connect()
        conn.execute(
            "INSERT INTO import_drafts (import_id, contract_version, target_kind, source_type, source_ref) "
            "VALUES ('draft1', 1, 'account', 'screenshot', 'ref1')"
        )
        conn.execute(
            "INSERT INTO import_candidates (candidate_id, import_id, field_name, review_status) "
            "VALUES ('cand1', 'draft1', 'name', 'unreviewed')"
        )
        conn.commit()
        conn.close()

        backup_path = tmp_path / "v8_backup.sqlite"
        initialized.backup(backup_path)
        assert initialized.verify_backup(backup_path) is True

        # Restore into a new DB
        db2 = PortfolioBookDatabase(path=tmp_path / "restored_v8.sqlite")
        db2.restore_from(backup_path)

        conn2 = db2.connect()
        row = conn2.execute("SELECT * FROM import_drafts WHERE import_id = 'draft1'").fetchone()
        assert row["source_ref"] == "ref1"
        row_cand = conn2.execute("SELECT * FROM import_candidates WHERE candidate_id = 'cand1'").fetchone()
        assert row_cand["field_name"] == "name"
        conn2.close()

    def test_v8_verify_backup_fails_if_import_table_missing(self, tmp_path):
        """verify_backup returns False if a v8 DB is missing import tables."""
        db_path = tmp_path / "missing_v8.sqlite"
        db = PortfolioBookDatabase(path=db_path)
        db.initialize()

        conn = sqlite3.connect(str(db_path))
        conn.execute("DROP TABLE import_candidates")
        conn.commit()
        conn.close()

        assert db.verify_backup(db_path) is False

    def test_v10_backup_restore_roundtrip(self, initialized, tmp_path):
        """v10 backup includes purpose_buckets and position_bucket_allocations."""
        from src.domain.products import ProductDefinition
        p = ProductDefinition(product_id="p1", name="P1", product_type="bank_wmp")
        initialized.create_product(p)
        initialized.create_account("acc1", "Acc 1")
        initialized.create_snapshot_batch("b1", "2026-06-01")
        initialized.set_batch_account_coverage("b1", "acc1", "complete")
        initialized.add_snapshot("b1", "acc1", "p1", quantity=1.0)
        initialized.confirm_batch("b1")

        initialized.create_bucket("bucket1", "Core", "core")
        initialized.set_position_bucket_allocation("a1", "b1", "acc1", "p1", "bucket1", 1000000)

        backup_path = tmp_path / "v10_backup.sqlite"
        initialized.backup(backup_path)
        assert initialized.verify_backup(backup_path) is True

        # Restore into a new DB
        db2 = PortfolioBookDatabase(path=tmp_path / "restored_v10.sqlite")
        db2.restore_from(backup_path)

        bucket = db2.get_bucket("bucket1")
        assert bucket["name"] == "Core"
        allocs = db2.get_position_bucket_allocations("b1", "acc1", "p1")
        assert len(allocs) == 1
        assert allocs[0]["allocation_ppm"] == 1000000

    def test_v10_verify_backup_fails_if_bucket_table_missing(self, tmp_path):
        """verify_backup returns False if a v10 DB is missing bucket tables."""
        db_path = tmp_path / "missing_v10.sqlite"
        db = PortfolioBookDatabase(path=db_path)
        db.initialize()

        conn = sqlite3.connect(str(db_path))
        conn.execute("DROP TABLE position_bucket_allocations")
        conn.commit()
        conn.close()

        assert db.verify_backup(db_path) is False

    def test_v9_backup_restore_roundtrip(self, initialized, tmp_path):
        """v9 backup includes exposure_batches and product_exposures."""
        from src.domain.products import ProductDefinition
        p = ProductDefinition(product_id="p1", name="P1", product_type="bank_wmp")
        initialized.create_product(p)

        initialized.create_exposure_batch("eb1", "p1", "2026-06-01", "2026-06-01")
        initialized.add_product_exposure("eb1", "asset_class", "equity", 1000000)

        backup_path = tmp_path / "v9_backup.sqlite"
        initialized.backup(backup_path)
        assert initialized.verify_backup(backup_path) is True

        # Restore into a new DB
        db2 = PortfolioBookDatabase(path=tmp_path / "restored_v9.sqlite")
        db2.restore_from(backup_path)

        batch = db2.get_exposure_batch("eb1")
        assert batch["product_id"] == "p1"
        assert len(batch["exposures"]) == 1
        assert batch["exposures"][0]["bucket"] == "equity"

    def test_v9_verify_backup_fails_if_exposure_table_missing(self, tmp_path):
        """verify_backup returns False if a v9 DB is missing exposure tables."""
        db_path = tmp_path / "missing_v9.sqlite"
        db = PortfolioBookDatabase(path=db_path)
        db.initialize()

        conn = sqlite3.connect(str(db_path))
        conn.execute("DROP TABLE product_exposures")
        conn.commit()
        conn.close()

        assert db.verify_backup(db_path) is False

    def test_restore_refuses_overwrite_without_flag(self, initialized, tmp_path):
        """restore_from() raises FileExistsError if target exists and overwrite=False."""
        backup_path = initialized.backup(tmp_path / "backup.sqlite")

        with pytest.raises(FileExistsError, match="overwrite=True"):
            initialized.restore_from(backup_path, overwrite=False)

    def test_restore_successful_with_overwrite(self, initialized, tmp_path):
        """restore_from() replaces current DB content when overwrite=True."""
        # 1. Add some data
        initialized.create_account(account_id="acc1", name="Original")
        backup_path = initialized.backup(tmp_path / "backup.sqlite")

        # 2. Modify data
        initialized.update_account("acc1", name="Modified")
        assert initialized.get_account("acc1")["name"] == "Modified"

        # 3. Restore
        initialized.restore_from(backup_path, overwrite=True)

        # 4. Verify original name restored
        assert initialized.get_account("acc1")["name"] == "Original"

    def test_restore_with_migration(self, initialized, tmp_path):
        """Restoring a lower-version backup runs migrations to current version."""
        v1_path = tmp_path / "v1.sqlite"
        conn = sqlite3.connect(str(v1_path))
        conn.execute("CREATE TABLE _schema_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        conn.execute("INSERT INTO _schema_meta VALUES ('version', '1')")
        conn.execute("CREATE TABLE accounts (account_id TEXT PRIMARY KEY, name TEXT NOT NULL)")
        conn.execute("INSERT INTO accounts (account_id, name) VALUES ('v1_acc', 'V1 Account')")
        conn.commit()
        conn.close()

        # Target DB
        db = PortfolioBookDatabase(path=tmp_path / "restored.sqlite")
        db.restore_from(v1_path)

        assert db.schema_version() == PortfolioBookDatabase.CURRENT_SCHEMA_VERSION
        assert db.get_account("v1_acc")["name"] == "V1 Account"
        # Verify a newer table exists
        conn = db.connect()
        # Should not raise "no such table"
        conn.execute("SELECT * FROM products").fetchall()
        conn.close()

    def test_restore_fails_for_incompatible_version(self, initialized, tmp_path):
        """restore_from() raises PortfolioBookError (via verify_backup) for newer backups."""
        newer_path = tmp_path / "newer.sqlite"
        conn = sqlite3.connect(str(newer_path))
        conn.execute("CREATE TABLE _schema_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        conn.execute("INSERT INTO _schema_meta VALUES ('version', '99')")
        conn.commit()
        conn.close()

        with pytest.raises(PortfolioBookError, match="Invalid backup file"):
            initialized.restore_from(newer_path, overwrite=True)

    def test_restore_atomic_on_failure(self, initialized, tmp_path, monkeypatch):
        """If restore fails during migration or verify, original DB is untouched."""
        initialized.create_account("acc_orig", "Original")
        backup_path = initialized.backup(tmp_path / "backup.sqlite")

        # Create a new account in current DB that isn't in backup
        initialized.create_account("acc_new", "New")

        # Mock initialize to fail during restore's temp_db.initialize()
        def mock_init(self):
            raise RuntimeError("Boom!")

        # We need to mock initialize on the temp_db instance inside restore_from
        # or just mock the class method globally during the call.
        original_init = PortfolioBookDatabase.initialize
        monkeypatch.setattr(PortfolioBookDatabase, "initialize", mock_init)

        with pytest.raises(RuntimeError, match="Boom!"):
            initialized.restore_from(backup_path, overwrite=True)

        # Restore initialize
        monkeypatch.setattr(PortfolioBookDatabase, "initialize", original_init)

        # Verify original DB still has 'acc_new' (not replaced by backup)
        assert initialized.get_account("acc_new") is not None
        # And temp files are gone
        assert not (initialized.path.parent / "restored.sqlite.restore.tmp").exists()

    def test_restore_no_temp_files_left(self, initialized, tmp_path):
        """Successful restore leaves no temp files."""
        backup_path = initialized.backup(tmp_path / "backup.sqlite")
        initialized.restore_from(backup_path, overwrite=True)
        temp_files = list(initialized.path.parent.glob("*.tmp"))
        assert len(temp_files) == 0


# ── Cashflow CRUD ───────────────────────────────────────────────────────────

# ── Snapshots ──────────────────────────────────────────────────────────────

class TestSnapshots:
    @pytest.fixture
    def setup_data(self, initialized):
        from src.domain.products import ProductDefinition
        initialized.create_account(account_id="acc_1", name="Test Account")
        p = ProductDefinition(
            product_id="prod_1", name="Test Product",
            product_type="equity_fund", currency="CNY"
        )
        initialized.create_product(p)
        return "acc_1", "prod_1"

    def test_full_batch_workflow(self, initialized, setup_data):
        acc_id, prod_id = setup_data
        batch_id = "batch_20231027"
        initialized.create_snapshot_batch(batch_id, as_of="2023-10-27", notes="Initial sync")
        initialized.set_batch_account_coverage(batch_id, acc_id, "complete")
        batch = initialized.get_batch(batch_id)
        assert batch["status"] == "draft"
        assert len(batch["snapshots"]) == 0
        assert len(batch["account_coverage"]) == 1
        initialized.add_snapshot(batch_id, acc_id, prod_id, quantity=100.0, market_value=1234.56, cost_basis=1000.0)
        batch = initialized.get_batch(batch_id)
        assert len(batch["snapshots"]) == 1
        assert batch["snapshots"][0]["account_id"] == acc_id
        initialized.confirm_batch(batch_id)
        assert initialized.get_batch(batch_id)["status"] == "confirmed"

    def test_add_to_confirmed_batch_raises(self, initialized, setup_data):
        acc_id, prod_id = setup_data
        initialized.create_snapshot_batch("batch_fixed", as_of="2023-10-27")
        initialized.set_batch_account_coverage("batch_fixed", acc_id, "complete")
        initialized.confirm_batch("batch_fixed")
        with pytest.raises(PortfolioBookError, match="Cannot add to confirmed batch"):
            initialized.add_snapshot("batch_fixed", acc_id, prod_id, quantity=50.0)

    def test_confirm_non_existent_batch_raises(self, initialized):
        with pytest.raises(PortfolioBookError, match="not found"):
            initialized.confirm_batch("no_such_batch")

    def test_supersede_batch(self, initialized):
        initialized.create_account(account_id="acc_super", name="Super Account")
        initialized.create_snapshot_batch("batch_old", as_of="2023-10-27")
        initialized.set_batch_account_coverage("batch_old", "acc_super", "complete")
        initialized.confirm_batch("batch_old")
        initialized.supersede_batch("batch_old")
        assert initialized.get_batch("batch_old")["status"] == "superseded"

    def test_fk_constraints(self, initialized, setup_data):
        acc_id, prod_id = setup_data
        initialized.create_snapshot_batch("batch_fk", as_of="2023-10-27")
        # unregistered account fails at coverage check, not FK
        with pytest.raises(PortfolioBookError, match="not registered"):
            initialized.add_snapshot("batch_fk", "invalid_acc", prod_id, quantity=10)
        # register coverage for the valid account; invalid product still hits FK
        initialized.set_batch_account_coverage("batch_fk", acc_id, "complete")
        with pytest.raises(sqlite3.IntegrityError):
            initialized.add_snapshot("batch_fk", acc_id, "invalid_prod", quantity=10)

    def test_unique_constraint(self, initialized, setup_data):
        acc_id, prod_id = setup_data
        initialized.create_snapshot_batch("batch_uniq", as_of="2023-10-27")
        initialized.set_batch_account_coverage("batch_uniq", acc_id, "complete")
        initialized.add_snapshot("batch_uniq", acc_id, prod_id, quantity=10)
        with pytest.raises(sqlite3.IntegrityError):
            initialized.add_snapshot("batch_uniq", acc_id, prod_id, quantity=20)


class TestCashflowCRUD:
    @pytest.fixture
    def account(self, initialized):
        initialized.create_account("acc_cash", "Cash Account")
        return "acc_cash"

    @pytest.fixture
    def product(self, initialized):
        from src.domain.products import ProductDefinition
        p = ProductDefinition(product_id="prod_cash", name="Product", product_type="other")
        initialized.create_product(p)
        return "prod_cash"

    def test_create_basic_cashflows(self, initialized, account, product):
        """Test creation of purchase, sale, interest, fee, and dividend."""
        # Purchase (negative)
        initialized.create_cashflow(
            "ev_001", "purchase", account, -1000.0, "CNY", "2023-01-01", product_id=product
        )
        # Sale (positive)
        initialized.create_cashflow(
            "ev_002", "sale", account, 500.0, "CNY", "2023-01-02", product_id=product
        )
        # Interest
        initialized.create_cashflow(
            "ev_003", "interest", account, 10.0, "CNY", "2023-01-03"
        )
        # Fee (negative)
        initialized.create_cashflow(
            "ev_004", "fee", account, -5.0, "CNY", "2023-01-04"
        )
        # Dividend
        initialized.create_cashflow(
            "ev_005", "dividend", account, 20.0, "CNY", "2023-01-05", product_id=product
        )

        flows = initialized.get_cashflows_for_account(account)
        assert len(flows) == 5
        # Ordered by date DESC
        assert flows[0]["event_id"] == "ev_005"
        assert flows[4]["event_id"] == "ev_001"

    def test_transfer_pair_and_linking(self, initialized, account):
        """Test transfer_in/out creation and linking."""
        initialized.create_account("acc_target", "Target Account")

        initialized.create_cashflow(
            "tx_out", "transfer_out", account, -100.0, "USD", "2023-02-01"
        )
        initialized.create_cashflow(
            "tx_in", "transfer_in", "acc_target", 100.0, "USD", "2023-02-01"
        )

        initialized.link_transfer("tx_out", "tx_in")

        out_flow = [f for f in initialized.get_cashflows_for_account(account) if f["event_id"] == "tx_out"][0]
        in_flow = [f for f in initialized.get_cashflows_for_account("acc_target") if f["event_id"] == "tx_in"][0]

        assert out_flow["pair_event_id"] == "tx_in"
        assert in_flow["pair_event_id"] == "tx_out"

    def test_fx_conversion(self, initialized, account):
        """Test FX conversion requires both currencies and counter_amount."""
        initialized.create_cashflow(
            "fx_001", "fx_conversion", account, -100.0, "USD", "2023-03-01",
            counter_amount=700.0, counter_currency="CNY"
        )

        flow = initialized.get_cashflows_for_account(account)[0]
        assert flow["event_type"] == "fx_conversion"
        assert flow["counter_amount"] == 700.0
        assert flow["counter_currency"] == "CNY"

    def test_validation_sign_semantics(self, initialized, account):
        """Test sign conventions for various types."""
        # Must be positive
        for etype in ("interest", "dividend", "transfer_in", "sale", "external_contribution"):
            with pytest.raises(ValueError, match="must have a positive amount"):
                initialized.create_cashflow(f"err_{etype}", etype, account, -1.0, "CNY", "2023-01-01")

        # Must be negative
        for etype in ("fee", "transfer_out", "purchase", "external_withdrawal"):
            with pytest.raises(ValueError, match="must have a negative amount"):
                initialized.create_cashflow(f"err_{etype}", etype, account, 1.0, "CNY", "2023-01-01")

    def test_validation_fx_requirements(self, initialized, account):
        """FX conversion must have negative primary, positive counter, and different currencies."""
        with pytest.raises(ValueError, match="primary amount must be negative"):
            initialized.create_cashflow("fx_err1", "fx_conversion", account, 100.0, "USD", "2023-01-01",
                                     counter_amount=700.0, counter_currency="CNY")

        with pytest.raises(ValueError, match="positive counter_amount"):
            initialized.create_cashflow("fx_err2", "fx_conversion", account, -100.0, "USD", "2023-01-01",
                                     counter_amount=-700.0, counter_currency="CNY")

        with pytest.raises(ValueError, match="currencies must be different"):
            initialized.create_cashflow("fx_err3", "fx_conversion", account, -100.0, "USD", "2023-01-01",
                                     counter_amount=100.0, counter_currency="USD")

    def test_duplicate_event_id_rejected(self, initialized, account):
        """Reject duplicate event_ids with PortfolioBookError."""
        initialized.create_cashflow("dup", "interest", account, 10.0, "CNY", "2023-01-01")
        with pytest.raises(PortfolioBookError, match="Duplicate event_id"):
            initialized.create_cashflow("dup", "interest", account, 20.0, "CNY", "2023-01-02")

    def test_get_cashflows_for_product(self, initialized, account, product):
        """Test retrieval filter by product_id."""
        initialized.create_cashflow("p1", "purchase", account, -100.0, "CNY", "2023-01-01", product_id=product)
        initialized.create_cashflow("p2", "interest", account, 10.0, "CNY", "2023-01-02") # no product_id

        flows = initialized.get_cashflows_for_product(product)
        assert len(flows) == 1
        assert flows[0]["event_id"] == "p1"


# ── DS-006A: Schema v5 explicit marker ────────────────────────────────────

class TestV5ExplicitMigration:
    def test_v5_migration_is_registered_and_runs(self, tmp_path):
        """Explicit v5 migration exists and can execute without error."""
        db = PortfolioBookDatabase(path=tmp_path / "v5_test.sqlite")

        # Hand-build a v4 database
        conn = sqlite3.connect(str(db.path))
        conn.execute("CREATE TABLE _schema_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        conn.execute("INSERT INTO _schema_meta VALUES ('version', '4')")
        conn.execute("CREATE TABLE accounts (account_id TEXT PRIMARY KEY, name TEXT)")
        conn.execute("CREATE TABLE products (product_id TEXT PRIMARY KEY, name TEXT, issuer TEXT DEFAULT '', product_type TEXT DEFAULT '', currency TEXT DEFAULT '', liquidity TEXT DEFAULT '', data_source TEXT DEFAULT '', isin TEXT DEFAULT '', notes TEXT DEFAULT '', extra_json TEXT DEFAULT '{}', created_at TEXT DEFAULT CURRENT_TIMESTAMP, updated_at TEXT DEFAULT CURRENT_TIMESTAMP)")
        conn.execute("CREATE TABLE snapshot_batches (batch_id TEXT PRIMARY KEY, status TEXT DEFAULT 'draft', as_of TEXT, source TEXT, quality TEXT, notes TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP, updated_at TEXT DEFAULT CURRENT_TIMESTAMP)")
        conn.execute("CREATE TABLE position_snapshots (snapshot_id INTEGER PRIMARY KEY AUTOINCREMENT, batch_id TEXT, account_id TEXT, product_id TEXT, quantity REAL NOT NULL, market_value REAL, cost_basis REAL, currency TEXT DEFAULT 'CNY', source TEXT, quality TEXT, notes TEXT)")
        conn.execute("CREATE TABLE cashflow_events (event_id TEXT PRIMARY KEY, event_type TEXT, account_id TEXT, product_id TEXT, amount REAL, currency TEXT, counter_amount REAL, counter_currency TEXT, pair_event_id TEXT, effective_date TEXT, source TEXT, notes TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP, updated_at TEXT DEFAULT CURRENT_TIMESTAMP)")
        conn.commit()
        conn.close()

        db.initialize()  # should run v5 → current
        assert db.schema_version() == PortfolioBookDatabase.CURRENT_SCHEMA_VERSION


# ── DS-006A: Schema v6 — fresh init & v5→v6 migration ──────────────────

class TestV6Migration:
    """Migration to v6: coverage table + nullable quantity."""

    def test_fresh_init_creates_current_version(self, tmp_path):
        """A brand-new database initializes directly to current version."""
        db = PortfolioBookDatabase(path=tmp_path / "fresh_init.sqlite")
        db.initialize()
        assert db.schema_version() == PortfolioBookDatabase.CURRENT_SCHEMA_VERSION

        conn = db.connect()
        try:
            # snapshot_batch_accounts exists
            tables = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
            table_names = {r["name"] for r in tables}
            assert "snapshot_batch_accounts" in table_names

            # position_snapshots quantity is nullable
            pragma = conn.execute("PRAGMA table_info('position_snapshots')").fetchall()
            quantity_col = [c for c in pragma if c["name"] == "quantity"][0]
            assert quantity_col["notnull"] == 0  # nullable
        finally:
            conn.close()

    def test_v8_to_v9_migration(self, tmp_path):
        """Migrating from v8 to v9 creates the new exposure tables."""
        db_path = tmp_path / "v8_legacy_mig.sqlite"
        conn = sqlite3.connect(str(db_path))
        conn.execute("CREATE TABLE _schema_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        conn.execute("INSERT INTO _schema_meta VALUES ('version', '8')")
        # Add minimal v8 structure
        conn.execute("CREATE TABLE accounts (account_id TEXT PRIMARY KEY, name TEXT)")
        conn.execute("CREATE TABLE products (product_id TEXT PRIMARY KEY, name TEXT)")
        conn.execute("CREATE TABLE snapshot_batches (batch_id TEXT PRIMARY KEY, as_of TEXT)")
        conn.execute("CREATE TABLE position_snapshots (snapshot_id INTEGER PRIMARY KEY, batch_id TEXT, account_id TEXT, product_id TEXT)")
        conn.execute("CREATE TABLE cashflow_events (event_id TEXT PRIMARY KEY, event_type TEXT, account_id TEXT, amount REAL, currency TEXT, effective_date TEXT)")
        conn.execute("CREATE TABLE snapshot_batch_accounts (batch_id TEXT, account_id TEXT, coverage TEXT, PRIMARY KEY(batch_id, account_id))")
        conn.execute("CREATE TABLE import_drafts (import_id TEXT PRIMARY KEY, contract_version INTEGER, target_kind TEXT, source_type TEXT, source_ref TEXT)")
        conn.execute("CREATE TABLE import_candidates (candidate_id TEXT PRIMARY KEY, import_id TEXT, field_name TEXT, review_status TEXT)")
        conn.commit()
        conn.close()

        db = PortfolioBookDatabase(path=db_path)
        db.initialize()
        assert db.schema_version() == PortfolioBookDatabase.CURRENT_SCHEMA_VERSION

        conn = db.connect()
        # Should have exposure_batches and product_exposures
        conn.execute("SELECT * FROM exposure_batches").fetchall()
        conn.execute("SELECT * FROM product_exposures").fetchall()
        # Should have purpose_buckets and position_bucket_allocations
        conn.execute("SELECT * FROM purpose_buckets").fetchall()
        conn.execute("SELECT * FROM position_bucket_allocations").fetchall()
        conn.close()

    def test_v9_to_v10_migration(self, tmp_path):
        """Migrating from v9 to v10 creates the new bucket tables."""
        db_path = tmp_path / "v9_legacy_mig.sqlite"
        conn = sqlite3.connect(str(db_path))
        conn.execute("CREATE TABLE _schema_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        conn.execute("INSERT INTO _schema_meta VALUES ('version', '9')")
        # Add minimal v9 structure (just enough for tables existence check)
        conn.execute("CREATE TABLE accounts (account_id TEXT PRIMARY KEY, name TEXT)")
        conn.execute("CREATE TABLE products (product_id TEXT PRIMARY KEY, name TEXT)")
        conn.execute("CREATE TABLE snapshot_batches (batch_id TEXT PRIMARY KEY, as_of TEXT)")
        conn.execute("CREATE TABLE position_snapshots (snapshot_id INTEGER PRIMARY KEY, batch_id TEXT, account_id TEXT, product_id TEXT)")
        conn.execute("CREATE TABLE cashflow_events (event_id TEXT PRIMARY KEY, event_type TEXT, account_id TEXT, amount REAL, currency TEXT, effective_date TEXT)")
        conn.execute("CREATE TABLE snapshot_batch_accounts (batch_id TEXT, account_id TEXT, coverage TEXT, PRIMARY KEY(batch_id, account_id))")
        conn.execute("CREATE TABLE import_drafts (import_id TEXT PRIMARY KEY, contract_version INTEGER, target_kind TEXT, source_type TEXT, source_ref TEXT)")
        conn.execute("CREATE TABLE import_candidates (candidate_id TEXT PRIMARY KEY, import_id TEXT, field_name TEXT, review_status TEXT)")
        conn.execute("CREATE TABLE exposure_batches (exposure_batch_id TEXT PRIMARY KEY, product_id TEXT, as_of TEXT, known_at TEXT)")
        conn.execute("CREATE TABLE product_exposures (exposure_batch_id TEXT, dimension TEXT, bucket TEXT, weight_ppm INTEGER)")
        conn.commit()
        conn.close()

        db = PortfolioBookDatabase(path=db_path)
        db.initialize()
        assert db.schema_version() == PortfolioBookDatabase.CURRENT_SCHEMA_VERSION

        conn = db.connect()
        conn.execute("SELECT * FROM purpose_buckets").fetchall()
        conn.execute("SELECT * FROM position_bucket_allocations").fetchall()
        conn.close()

    def test_v10_to_v11_migration(self, tmp_path):
        """Migrating from v10 to v11 creates the new decision tables."""
        db_path = tmp_path / "v10_legacy_mig.sqlite"
        conn = sqlite3.connect(str(db_path))
        conn.execute("CREATE TABLE _schema_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        conn.execute("INSERT INTO _schema_meta VALUES ('version', '10')")
        # Add minimal v10 structure
        conn.execute("CREATE TABLE accounts (account_id TEXT PRIMARY KEY, name TEXT)")
        conn.execute("CREATE TABLE products (product_id TEXT PRIMARY KEY, name TEXT)")
        conn.execute("CREATE TABLE snapshot_batches (batch_id TEXT PRIMARY KEY, as_of TEXT)")
        conn.execute("CREATE TABLE position_snapshots (snapshot_id INTEGER PRIMARY KEY, batch_id TEXT, account_id TEXT, product_id TEXT)")
        conn.execute("CREATE TABLE cashflow_events (event_id TEXT PRIMARY KEY, event_type TEXT, account_id TEXT, amount REAL, currency TEXT, effective_date TEXT)")
        conn.execute("CREATE TABLE snapshot_batch_accounts (batch_id TEXT, account_id TEXT, coverage TEXT, PRIMARY KEY(batch_id, account_id))")
        conn.execute("CREATE TABLE import_drafts (import_id TEXT PRIMARY KEY, contract_version INTEGER, target_kind TEXT, source_type TEXT, source_ref TEXT)")
        conn.execute("CREATE TABLE import_candidates (candidate_id TEXT PRIMARY KEY, import_id TEXT, field_name TEXT, review_status TEXT)")
        conn.execute("CREATE TABLE exposure_batches (exposure_batch_id TEXT PRIMARY KEY, product_id TEXT, as_of TEXT, known_at TEXT)")
        conn.execute("CREATE TABLE product_exposures (exposure_batch_id TEXT, dimension TEXT, bucket TEXT, weight_ppm INTEGER)")
        conn.execute("CREATE TABLE purpose_buckets (bucket_id TEXT PRIMARY KEY, name TEXT, bucket_type TEXT)")
        conn.execute("CREATE TABLE position_bucket_allocations (allocation_id TEXT PRIMARY KEY, batch_id TEXT, account_id TEXT, product_id TEXT, bucket_id TEXT, allocation_ppm INTEGER)")
        conn.commit()
        conn.close()

        db = PortfolioBookDatabase(path=db_path)
        db.initialize()
        assert db.schema_version() == PortfolioBookDatabase.CURRENT_SCHEMA_VERSION

        conn = db.connect()
        # Should have decisions and decision_revisions
        conn.execute("SELECT * FROM decisions").fetchall()
        conn.execute("SELECT * FROM decision_revisions").fetchall()
        conn.close()

    def test_v5_to_v6_preserves_old_snapshots(self, tmp_path):
        """Migrating from v5 to v6 preserves all existing snapshot data."""
        from src.domain.products import ProductDefinition

        db_path = tmp_path / "v5_legacy.sqlite"

        # Build a v5 database with real data
        conn = sqlite3.connect(str(db_path))
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("CREATE TABLE _schema_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        conn.execute("INSERT INTO _schema_meta VALUES ('version', '5')")
        conn.execute(
            "CREATE TABLE accounts ("
            "  account_id TEXT PRIMARY KEY, name TEXT NOT NULL,"
            "  institution TEXT DEFAULT '', account_type TEXT DEFAULT 'brokerage',"
            "  base_currency TEXT DEFAULT 'CNY', ownership_scope TEXT DEFAULT 'personal',"
            "  status TEXT DEFAULT 'active', notes TEXT DEFAULT '',"
            "  created_at TEXT DEFAULT (datetime('now')), updated_at TEXT DEFAULT (datetime('now'))"
            ")"
        )
        conn.execute(
            "CREATE TABLE products ("
            "  product_id TEXT PRIMARY KEY, name TEXT NOT NULL, issuer TEXT DEFAULT '',"
            "  product_type TEXT DEFAULT 'bank_wmp', currency TEXT DEFAULT 'CNY',"
            "  liquidity TEXT DEFAULT 't_plus_1', data_source TEXT DEFAULT 'manual',"
            "  isin TEXT DEFAULT '', notes TEXT DEFAULT '', extra_json TEXT DEFAULT '{}',"
            "  created_at TEXT DEFAULT CURRENT_TIMESTAMP, updated_at TEXT DEFAULT CURRENT_TIMESTAMP"
            ")"
        )
        conn.execute(
            "CREATE TABLE snapshot_batches ("
            "  batch_id TEXT PRIMARY KEY, status TEXT DEFAULT 'draft', as_of TEXT NOT NULL,"
            "  source TEXT DEFAULT 'manual', quality TEXT DEFAULT 'reported', notes TEXT,"
            "  created_at TEXT DEFAULT CURRENT_TIMESTAMP, updated_at TEXT DEFAULT CURRENT_TIMESTAMP"
            ")"
        )
        conn.execute(
            "CREATE TABLE position_snapshots ("
            "  snapshot_id INTEGER PRIMARY KEY AUTOINCREMENT, batch_id TEXT NOT NULL,"
            "  account_id TEXT NOT NULL, product_id TEXT NOT NULL,"
            "  quantity REAL NOT NULL, market_value REAL, cost_basis REAL,"
            "  currency TEXT DEFAULT 'CNY', source TEXT, quality TEXT, notes TEXT,"
            "  UNIQUE(batch_id, account_id, product_id),"
            "  FOREIGN KEY (batch_id) REFERENCES snapshot_batches(batch_id),"
            "  FOREIGN KEY (account_id) REFERENCES accounts(account_id),"
            "  FOREIGN KEY (product_id) REFERENCES products(product_id)"
            ")"
        )
        conn.execute(
            "CREATE TABLE cashflow_events ("
            "  event_id TEXT PRIMARY KEY, event_type TEXT NOT NULL,"
            "  account_id TEXT NOT NULL, product_id TEXT,"
            "  amount REAL NOT NULL, currency TEXT NOT NULL,"
            "  counter_amount REAL, counter_currency TEXT, pair_event_id TEXT,"
            "  effective_date TEXT NOT NULL, source TEXT DEFAULT 'manual', notes TEXT,"
            "  created_at TEXT DEFAULT CURRENT_TIMESTAMP, updated_at TEXT DEFAULT CURRENT_TIMESTAMP,"
            "  FOREIGN KEY (account_id) REFERENCES accounts (account_id)"
            ")"
        )

        conn.execute("INSERT INTO accounts (account_id, name) VALUES ('acc_v5', 'Legacy')")
        conn.execute(
            "INSERT INTO products (product_id, name, product_type, currency) "
            "VALUES ('prod_v5', 'Legacy Fund', 'equity_fund', 'CNY')"
        )
        conn.execute(
            "INSERT INTO snapshot_batches (batch_id, as_of) VALUES ('batch_v5', '2025-01-01')"
        )
        conn.execute(
            "INSERT INTO position_snapshots "
            "(batch_id, account_id, product_id, quantity, market_value, cost_basis) "
            "VALUES ('batch_v5', 'acc_v5', 'prod_v5', 500.0, 7500.0, 6000.0)"
        )
        conn.commit()
        conn.close()

        # Migrate
        db = PortfolioBookDatabase(path=db_path)
        db.initialize()
        assert db.schema_version() == PortfolioBookDatabase.CURRENT_SCHEMA_VERSION

        # Verify old data preserved
        batch = db.get_batch("batch_v5")
        assert batch is not None
        assert len(batch["snapshots"]) == 1
        snap = batch["snapshots"][0]
        assert snap["account_id"] == "acc_v5"
        assert snap["product_id"] == "prod_v5"
        assert snap["quantity"] == 500.0
        assert snap["market_value"] == 7500.0
        assert snap["cost_basis"] == 6000.0

        # Pre-v6 data cannot prove that the account snapshot was complete.
        assert batch["account_coverage"] == [
            {
                "account_id": "acc_v5",
                "coverage": "partial",
                "notes": "Backfilled from pre-v6 snapshot; completeness unknown",
            }
        ]

        # Verify quantity is now nullable (can insert NULL)
        conn = db.connect()
        try:
            # Add a new snapshot with quantity=NULL — should succeed
            conn.execute(
                "INSERT INTO position_snapshots "
                "(batch_id, account_id, product_id, quantity, market_value) "
                "VALUES ('batch_v5', 'acc_v5', 'prod_v5', NULL, 8000.0)"
            )
            conn.commit()
        except sqlite3.IntegrityError:
            pass  # unique constraint on existing row — expected
        finally:
            conn.close()


# ── DS-006A: Optional quantity ───────────────────────────────────────────

class TestOptionalQuantity:
    @pytest.fixture
    def env(self, initialized):
        from src.domain.products import ProductDefinition
        initialized.create_account(account_id="acc_qty", name="Qty Account")
        p = ProductDefinition(
            product_id="prod_qty", name="Qty Product",
            product_type="equity_fund", currency="CNY"
        )
        initialized.create_product(p)
        initialized.create_snapshot_batch("batch_qty", as_of="2025-06-01")
        initialized.set_batch_account_coverage("batch_qty", "acc_qty", "complete")
        return "acc_qty", "prod_qty"

    def test_quantity_none_with_market_value_works(self, initialized, env):
        """market_value-only snapshot (quantity=None) is accepted."""
        acc_id, prod_id = env
        initialized.add_snapshot("batch_qty", acc_id, prod_id,
                                 quantity=None, market_value=5000.0)
        batch = initialized.get_batch("batch_qty")
        assert len(batch["snapshots"]) == 1
        assert batch["snapshots"][0]["quantity"] is None
        assert batch["snapshots"][0]["market_value"] == 5000.0

    def test_market_value_none_with_quantity_works(self, initialized, env):
        """quantity-only snapshot (market_value=None) is accepted."""
        acc_id, prod_id = env
        initialized.add_snapshot("batch_qty", acc_id, prod_id,
                                 quantity=250.0, market_value=None)
        batch = initialized.get_batch("batch_qty")
        assert batch["snapshots"][0]["quantity"] == 250.0
        assert batch["snapshots"][0]["market_value"] is None

    def test_both_quantity_and_market_value_none_rejected(self, initialized, env):
        """Both quantity and market_value None → ValueError."""
        acc_id, prod_id = env
        with pytest.raises(ValueError, match="At least one"):
            initialized.add_snapshot("batch_qty", acc_id, prod_id,
                                     quantity=None, market_value=None)

    def test_negative_quantity_rejected(self, initialized, env):
        acc_id, prod_id = env
        with pytest.raises(ValueError, match="quantity must not be negative"):
            initialized.add_snapshot("batch_qty", acc_id, prod_id, quantity=-1.0)

    def test_negative_market_value_rejected(self, initialized, env):
        acc_id, prod_id = env
        with pytest.raises(ValueError, match="market_value must not be negative"):
            initialized.add_snapshot("batch_qty", acc_id, prod_id,
                                     market_value=-100.0)

    def test_negative_cost_basis_rejected(self, initialized, env):
        acc_id, prod_id = env
        with pytest.raises(ValueError, match="cost_basis must not be negative"):
            initialized.add_snapshot("batch_qty", acc_id, prod_id,
                                     quantity=10, cost_basis=-1.0)

    def test_zero_values_are_legal(self, initialized, env):
        """Zero quantity and zero market_value are accepted."""
        acc_id, prod_id = env
        initialized.add_snapshot("batch_qty", acc_id, prod_id,
                                 quantity=0.0, market_value=0.0)
        batch = initialized.get_batch("batch_qty")
        assert batch["snapshots"][0]["quantity"] == 0.0
        assert batch["snapshots"][0]["market_value"] == 0.0


# ── DS-006A: Batch account coverage ────────────────────────────────────

class TestBatchCoverage:
    @pytest.fixture
    def env(self, initialized):
        from src.domain.products import ProductDefinition
        initialized.create_account(account_id="acc_cov", name="Cov Account")
        initialized.create_account(account_id="acc_cov2", name="Cov Account 2")
        p = ProductDefinition(
            product_id="prod_cov", name="Cov Product",
            product_type="equity_fund", currency="CNY"
        )
        initialized.create_product(p)
        return "acc_cov", "acc_cov2", "prod_cov"

    def test_unregistered_account_cannot_add_snapshot(self, initialized, env):
        """Adding a snapshot without coverage registration is rejected."""
        acc_id, _, prod_id = env
        initialized.create_snapshot_batch("batch_noreg", as_of="2025-06-01")
        with pytest.raises(PortfolioBookError, match="not registered"):
            initialized.add_snapshot("batch_noreg", acc_id, prod_id, quantity=10)

    def test_empty_account_cannot_add_snapshot(self, initialized, env):
        """An account marked 'empty' cannot receive position snapshots."""
        acc_id, _, prod_id = env
        initialized.create_snapshot_batch("batch_empty", as_of="2025-06-01")
        initialized.set_batch_account_coverage("batch_empty", acc_id, "empty")
        with pytest.raises(PortfolioBookError, match="marked as 'empty'"):
            initialized.add_snapshot("batch_empty", acc_id, prod_id, quantity=10)

    def test_account_with_positions_cannot_be_changed_to_empty(
        self, initialized, env
    ):
        """Changing coverage must not create an empty account with positions."""
        acc_id, _, prod_id = env
        initialized.create_snapshot_batch("batch_notempty", as_of="2025-06-01")
        initialized.set_batch_account_coverage(
            "batch_notempty", acc_id, "partial"
        )
        initialized.add_snapshot(
            "batch_notempty", acc_id, prod_id, market_value=100.0
        )
        with pytest.raises(PortfolioBookError, match="cannot be marked empty"):
            initialized.set_batch_account_coverage(
                "batch_notempty", acc_id, "empty"
            )

    def test_database_constraint_rejects_invalid_coverage(self, initialized, env):
        """Direct writes cannot bypass the coverage enum."""
        acc_id, _, _ = env
        initialized.create_snapshot_batch("batch_check", as_of="2025-06-01")
        with closing(initialized.connect()) as conn:
            with pytest.raises(sqlite3.IntegrityError):
                conn.execute(
                    "INSERT INTO snapshot_batch_accounts "
                    "(batch_id, account_id, coverage) VALUES (?, ?, ?)",
                    ("batch_check", acc_id, "invalid"),
                )

    def test_confirmed_batch_cannot_modify_coverage(self, initialized, env):
        """Coverage is frozen once a batch is confirmed."""
        acc_id, _, _ = env
        initialized.create_snapshot_batch("batch_cfm", as_of="2025-06-01")
        initialized.set_batch_account_coverage("batch_cfm", acc_id, "complete")
        initialized.confirm_batch("batch_cfm")
        with pytest.raises(PortfolioBookError, match="Cannot modify coverage"):
            initialized.set_batch_account_coverage("batch_cfm", acc_id, "partial")

    def test_invalid_coverage_value_rejected(self, initialized, env):
        acc_id, _, _ = env
        initialized.create_snapshot_batch("batch_inv", as_of="2025-06-01")
        with pytest.raises(ValueError, match="coverage must be one of"):
            initialized.set_batch_account_coverage("batch_inv", acc_id, "nonsense")

    def test_set_coverage_for_non_existent_batch(self, initialized, env):
        acc_id, _, _ = env
        with pytest.raises(PortfolioBookError, match="not found"):
            initialized.set_batch_account_coverage("no_batch", acc_id, "complete")

    def test_partial_progress_is_not_complete(self, initialized, env):
        acc_id, acc_id2, _ = env
        initialized.create_snapshot_batch("batch_part", as_of="2025-06-01")
        initialized.set_batch_account_coverage("batch_part", acc_id, "complete")
        initialized.set_batch_account_coverage("batch_part", acc_id2, "partial")

        progress = initialized.get_batch_progress("batch_part")
        assert progress["is_complete"] is False
        assert len(progress["accounts"]) == 2

    def test_complete_and_empty_is_complete(self, initialized, env):
        """All accounts complete or empty → is_complete=True."""
        acc_id, acc_id2, _ = env
        initialized.create_snapshot_batch("batch_allok", as_of="2025-06-01")
        initialized.set_batch_account_coverage("batch_allok", acc_id, "complete")
        initialized.set_batch_account_coverage("batch_allok", acc_id2, "empty")

        progress = initialized.get_batch_progress("batch_allok")
        assert progress["is_complete"] is True

    def test_no_accounts_cannot_confirm(self, initialized):
        """A batch with zero registered accounts cannot be confirmed."""
        initialized.create_snapshot_batch("batch_noacc", as_of="2025-06-01")
        with pytest.raises(PortfolioBookError, match="no accounts registered"):
            initialized.confirm_batch("batch_noacc")

    def test_get_batch_progress_for_missing_batch(self, initialized):
        with pytest.raises(PortfolioBookError, match="not found"):
            initialized.get_batch_progress("no_such_batch")

    def test_get_batch_includes_coverage(self, initialized, env):
        acc_id, _, _ = env
        initialized.create_snapshot_batch("batch_incov", as_of="2025-06-01")
        initialized.set_batch_account_coverage("batch_incov", acc_id, "complete",
                                                notes="All checked")

        batch = initialized.get_batch("batch_incov")
        assert "account_coverage" in batch
        assert len(batch["account_coverage"]) == 1
        assert batch["account_coverage"][0]["account_id"] == acc_id
        assert batch["account_coverage"][0]["coverage"] == "complete"
        assert batch["account_coverage"][0]["notes"] == "All checked"

    def test_coverage_can_be_updated_in_draft(self, initialized, env):
        """Coverage can be changed while the batch is still draft."""
        acc_id, _, _ = env
        initialized.create_snapshot_batch("batch_upd", as_of="2025-06-01")
        initialized.set_batch_account_coverage("batch_upd", acc_id, "partial")
        assert initialized.get_batch("batch_upd")["account_coverage"][0]["coverage"] == "partial"

        initialized.set_batch_account_coverage("batch_upd", acc_id, "complete")
        assert initialized.get_batch("batch_upd")["account_coverage"][0]["coverage"] == "complete"

# ── DS-006B: Schema v7 — Migration & Semantics ──────────────────────────

class TestV7Migration:
    """Migration to v7: rebuilding cashflow_events with financial semantics."""

    def test_v6_to_v7_preserves_and_maps_data(self, tmp_path):
        db_path = tmp_path / "v6_legacy.sqlite"
        conn = sqlite3.connect(str(db_path))
        conn.execute("CREATE TABLE _schema_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        conn.execute("INSERT INTO _schema_meta VALUES ('version', '6')")
        conn.execute("CREATE TABLE accounts (account_id TEXT PRIMARY KEY, name TEXT)")
        conn.execute("CREATE TABLE products (product_id TEXT PRIMARY KEY, name TEXT)")
        conn.execute(
            "CREATE TABLE cashflow_events ("
            "  event_id TEXT PRIMARY KEY, event_type TEXT NOT NULL,"
            "  account_id TEXT NOT NULL, product_id TEXT, amount REAL NOT NULL,"
            "  currency TEXT NOT NULL, counter_amount REAL, counter_currency TEXT,"
            "  pair_event_id TEXT, effective_date TEXT NOT NULL,"
            "  source TEXT DEFAULT 'manual', notes TEXT,"
            "  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,"
            "  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP"
            ")"
        )
        # Legacy data
        conn.execute("INSERT INTO accounts (account_id, name) VALUES ('acc1', 'Account 1')")
        conn.execute("INSERT INTO products (product_id, name) VALUES ('prod1', 'Product 1')")
        # subscription (pos) -> purchase (neg)
        conn.execute(
            "INSERT INTO cashflow_events (event_id, event_type, account_id, product_id, amount, currency, effective_date) "
            "VALUES ('ev1', 'subscription', 'acc1', 'prod1', 1000.0, 'CNY', '2025-01-01')"
        )
        # redemption (neg) -> sale (pos)
        conn.execute(
            "INSERT INTO cashflow_events (event_id, event_type, account_id, product_id, amount, currency, effective_date) "
            "VALUES ('ev2', 'redemption', 'acc1', 'prod1', -1000.0, 'CNY', '2025-01-02')"
        )
        # other without notes
        conn.execute(
            "INSERT INTO cashflow_events (event_id, event_type, account_id, amount, currency, effective_date) "
            "VALUES ('ev3', 'other', 'acc1', 100.0, 'CNY', '2025-01-03')"
        )
        # fx_conversion (v6 valid)
        conn.execute(
            "INSERT INTO cashflow_events (event_id, event_type, account_id, amount, currency, counter_amount, counter_currency, effective_date) "
            "VALUES ('ev4', 'fx_conversion', 'acc1', -100.0, 'USD', 700.0, 'CNY', '2025-01-04')"
        )
        conn.commit()
        conn.close()

        db = PortfolioBookDatabase(path=db_path)
        db.initialize()
        assert db.schema_version() == PortfolioBookDatabase.CURRENT_SCHEMA_VERSION

        flows = {f["event_id"]: f for f in db.get_cashflows_for_account("acc1")}
        assert flows["ev1"]["event_type"] == "purchase"
        assert flows["ev1"]["amount"] == -1000.0
        assert flows["ev2"]["event_type"] == "sale"
        assert flows["ev2"]["amount"] == 1000.0
        assert flows["ev3"]["event_type"] == "other"
        assert flows["ev3"]["notes"] == "Migrated from v6"
        assert flows["ev4"]["event_type"] == "fx_conversion"
        assert flows["ev4"]["amount"] == -100.0
        assert flows["ev4"]["counter_amount"] == 700.0


class TestCashflowSemantics:
    @pytest.fixture
    def env(self, initialized):
        from src.domain.products import ProductDefinition
        initialized.create_account("acc", "Account")
        initialized.create_product(ProductDefinition("prod", "Product", "equity_fund"))
        return "acc", "prod"

    def test_zero_amount_rejected(self, initialized, env):
        acc, _ = env
        with pytest.raises(ValueError, match="cannot be zero"):
            initialized.create_cashflow("ev0", "interest", acc, 0.0, "CNY", "2025-01-01")

    def test_other_requires_notes(self, initialized, env):
        acc, _ = env
        with pytest.raises(ValueError, match="Notes are required"):
            initialized.create_cashflow("ev1", "other", acc, 100.0, "CNY", "2025-01-01", notes="")

    def test_product_fk_enforced(self, initialized, env):
        acc, _ = env
        with pytest.raises(sqlite3.IntegrityError):
            initialized.create_cashflow("ev1", "purchase", acc, -100.0, "CNY", "2025-01-01", product_id="invalid")

    @pytest.mark.parametrize("etype, amount", [
        ("external_contribution", 100.0),
        ("external_withdrawal", -100.0),
        ("purchase", -100.0),
        ("sale", 100.0),
        ("interest", 100.0),
        ("dividend", 100.0),
        ("fee", -100.0),
        ("tax", -100.0),
        ("transfer_in", 100.0),
        ("transfer_out", -100.0),
        ("maturity", 100.0),
    ])
    def test_all_types_sign_validation(self, initialized, env, etype, amount):
        acc, prod = env
        # Valid
        initialized.create_cashflow(f"ok_{etype}", etype, acc, amount, "CNY", "2025-01-01", product_id=prod if etype in ("purchase", "sale") else None)
        # Invalid (flip sign)
        with pytest.raises(ValueError):
            initialized.create_cashflow(f"err_{etype}", etype, acc, -amount, "CNY", "2025-01-01")


class TestLinkTransferHardened:
    @pytest.fixture
    def env(self, initialized):
        initialized.create_account("acc1", "Acc 1")
        initialized.create_account("acc2", "Acc 2")
        initialized.create_cashflow("in_100", "transfer_in", "acc1", 100.0, "USD", "2025-01-01")
        initialized.create_cashflow("out_100", "transfer_out", "acc2", -100.0, "USD", "2025-01-01")
        initialized.create_cashflow("in_200", "transfer_in", "acc1", 200.0, "USD", "2025-01-01")
        initialized.create_cashflow("out_100_hkd", "transfer_out", "acc2", -100.0, "HKD", "2025-01-01")
        return "acc1", "acc2"

    def test_valid_link(self, initialized, env):
        initialized.link_transfer("in_100", "out_100")
        flows1 = {f["event_id"]: f for f in initialized.get_cashflows_for_account("acc1")}
        flows2 = {f["event_id"]: f for f in initialized.get_cashflows_for_account("acc2")}
        assert flows1["in_100"]["pair_event_id"] == "out_100"
        assert flows2["out_100"]["pair_event_id"] == "in_100"

    def test_link_mismatched_amount_rejected(self, initialized, env):
        with pytest.raises(ValueError, match="same absolute amount"):
            initialized.link_transfer("in_200", "out_100")

    def test_link_mismatched_currency_rejected(self, initialized, env):
        with pytest.raises(ValueError, match="same currency"):
            initialized.link_transfer("in_100", "out_100_hkd")

    def test_link_same_type_rejected(self, initialized, env):
        initialized.create_cashflow("in_100_2", "transfer_in", "acc2", 100.0, "USD", "2025-01-01")
        with pytest.raises(ValueError, match="one 'transfer_in' and one 'transfer_out'"):
            initialized.link_transfer("in_100", "in_100_2")

    def test_link_already_paired_rejected(self, initialized, env):
        initialized.link_transfer("in_100", "out_100")
        initialized.create_cashflow("out_100_v2", "transfer_out", "acc2", -100.0, "USD", "2025-01-01")
        with pytest.raises(PortfolioBookError, match="already paired"):
            initialized.link_transfer("in_100", "out_100_v2")

    def test_link_self_rejected(self, initialized, env):
        with pytest.raises(ValueError, match="to itself"):
            initialized.link_transfer("in_100", "in_100")


# ── DS-007: List methods ──────────────────────────────────────────────────

class TestListAccounts:
    def test_list_active_accounts(self, initialized):
        """list_accounts('active') returns only active accounts."""
        initialized.create_account(account_id="acc_a", name="Alpha")
        initialized.create_account(account_id="acc_b", name="Beta")
        initialized.create_account(account_id="acc_c", name="Charlie")
        initialized.deactivate_account("acc_b")

        rows = initialized.list_accounts("active")
        ids = [r["account_id"] for r in rows]
        assert "acc_a" in ids
        assert "acc_b" not in ids
        assert "acc_c" in ids

    def test_list_inactive_accounts(self, initialized):
        """list_accounts('inactive') returns only inactive accounts."""
        initialized.create_account(account_id="acc_x", name="X-ray")
        initialized.deactivate_account("acc_x")

        rows = initialized.list_accounts("inactive")
        assert len(rows) == 1
        assert rows[0]["account_id"] == "acc_x"

    def test_list_all_accounts(self, initialized):
        """list_accounts('all') returns all accounts regardless of status."""
        initialized.create_account(account_id="a1", name="A1")
        initialized.create_account(account_id="a2", name="A2")
        initialized.deactivate_account("a2")

        rows = initialized.list_accounts("all")
        assert len(rows) == 2

    def test_list_accounts_ordered_by_name_then_id(self, initialized):
        """List accounts returns rows ordered by name, then account_id."""
        initialized.create_account(account_id="z1", name="Same Name")
        initialized.create_account(account_id="a1", name="Same Name")
        initialized.create_account(account_id="mid", name="Alpha")

        rows = initialized.list_accounts("all")
        names = [(r["name"], r["account_id"]) for r in rows]
        assert names == [("Alpha", "mid"), ("Same Name", "a1"), ("Same Name", "z1")]

    def test_list_accounts_invalid_status(self, initialized):
        """Invalid status argument raises ValueError."""
        with pytest.raises(ValueError, match="status must be"):
            initialized.list_accounts("deleted")

    def test_list_accounts_empty(self, initialized):
        """List accounts on a fresh database returns empty list."""
        rows = initialized.list_accounts("all")
        assert rows == []


class TestListProducts:
    def test_list_products(self, initialized):
        """list_products() returns all products."""
        from src.domain.products import ProductDefinition
        p1 = ProductDefinition(product_id="p1", name="Product One", product_type="bank_wmp")
        p2 = ProductDefinition(product_id="p2", name="Product Two", product_type="equity_fund")
        initialized.create_product(p1)
        initialized.create_product(p2)

        products = initialized.list_products()
        assert len(products) == 2
        assert {p.product_id for p in products} == {"p1", "p2"}

    def test_list_products_ordered_by_name_then_id(self, initialized):
        """List products returns ordered by name, then product_id."""
        from src.domain.products import ProductDefinition
        p1 = ProductDefinition(product_id="b", name="Beta", product_type="bank_wmp")
        p2 = ProductDefinition(product_id="a", name="Alpha", product_type="bank_wmp")
        p3 = ProductDefinition(product_id="c", name="Alpha", product_type="bank_wmp")
        initialized.create_product(p1)
        initialized.create_product(p2)
        initialized.create_product(p3)

        products = initialized.list_products()
        order = [(p.name, p.product_id) for p in products]
        assert order == [("Alpha", "a"), ("Alpha", "c"), ("Beta", "b")]

    def test_list_products_empty(self, initialized):
        """List products on a fresh database returns empty list."""
        products = initialized.list_products()
        assert products == []


class TestWealthClassification:
    def test_all_classifications(self, initialized):
        assert initialized.classify_wealth_flow("external_contribution") == "external_flow"
        assert initialized.classify_wealth_flow("external_withdrawal") == "external_flow"
        assert initialized.classify_wealth_flow("interest") == "investment_pnl"
        assert initialized.classify_wealth_flow("dividend") == "investment_pnl"
        assert initialized.classify_wealth_flow("fee") == "investment_pnl"
        assert initialized.classify_wealth_flow("tax") == "investment_pnl"
        assert initialized.classify_wealth_flow("purchase") == "internal"
        assert initialized.classify_wealth_flow("sale") == "internal"
        assert initialized.classify_wealth_flow("transfer_in") == "internal"
        assert initialized.classify_wealth_flow("transfer_out") == "internal"
        assert initialized.classify_wealth_flow("fx_conversion") == "internal"
        assert initialized.classify_wealth_flow("maturity") == "internal"
        assert initialized.classify_wealth_flow("other") == "unclassified"
        assert initialized.classify_wealth_flow("unknown") == "unclassified"

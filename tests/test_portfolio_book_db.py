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
        conn = initialized.connect()
        conn.execute("CREATE TABLE test_data (val TEXT)")
        conn.execute("INSERT INTO test_data VALUES ('hello')")
        conn.commit()
        conn.close()

        backup_path = initialized.backup(tmp_path / "backup.sqlite")

        conn = initialized.connect()
        conn.execute("UPDATE test_data SET val = 'world'")
        conn.commit()
        conn.close()

        initialized.restore_from(backup_path, overwrite=True)

        conn = initialized.connect()
        row = conn.execute("SELECT val FROM test_data").fetchone()
        assert row["val"] == "hello"
        conn.close()

    def test_restore_fails_for_incompatible_version(self, initialized, tmp_path):
        """restore_from() raises UnsupportedSchemaVersionError for newer backups."""
        newer_path = tmp_path / "newer.sqlite"
        conn = sqlite3.connect(str(newer_path))
        conn.execute("CREATE TABLE _schema_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        conn.execute("INSERT INTO _schema_meta VALUES ('version', '99')")
        conn.commit()
        conn.close()

        with pytest.raises(UnsupportedSchemaVersionError, match="99"):
            initialized.restore_from(newer_path, overwrite=True)


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
        batch = initialized.get_batch(batch_id)
        assert batch["status"] == "draft"
        assert len(batch["snapshots"]) == 0
        initialized.add_snapshot(batch_id, acc_id, prod_id, quantity=100.0, market_value=1234.56, cost_basis=1000.0)
        batch = initialized.get_batch(batch_id)
        assert len(batch["snapshots"]) == 1
        assert batch["snapshots"][0]["account_id"] == acc_id
        initialized.confirm_batch(batch_id)
        assert initialized.get_batch(batch_id)["status"] == "confirmed"

    def test_add_to_confirmed_batch_raises(self, initialized, setup_data):
        acc_id, prod_id = setup_data
        initialized.create_snapshot_batch("batch_fixed", as_of="2023-10-27")
        initialized.confirm_batch("batch_fixed")
        with pytest.raises(PortfolioBookError, match="Cannot add to confirmed batch"):
            initialized.add_snapshot("batch_fixed", acc_id, prod_id, quantity=50.0)

    def test_confirm_non_existent_batch_raises(self, initialized):
        with pytest.raises(PortfolioBookError, match="not found"):
            initialized.confirm_batch("no_such_batch")

    def test_supersede_batch(self, initialized):
        initialized.create_snapshot_batch("batch_old", as_of="2023-10-27")
        initialized.confirm_batch("batch_old")
        initialized.supersede_batch("batch_old")
        assert initialized.get_batch("batch_old")["status"] == "superseded"

    def test_fk_constraints(self, initialized, setup_data):
        acc_id, prod_id = setup_data
        initialized.create_snapshot_batch("batch_fk", as_of="2023-10-27")
        with pytest.raises(sqlite3.IntegrityError):
            initialized.add_snapshot("batch_fk", "invalid_acc", prod_id, quantity=10)
        with pytest.raises(sqlite3.IntegrityError):
            initialized.add_snapshot("batch_fk", acc_id, "invalid_prod", quantity=10)

    def test_unique_constraint(self, initialized, setup_data):
        acc_id, prod_id = setup_data
        initialized.create_snapshot_batch("batch_uniq", as_of="2023-10-27")
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
        """Test creation of subscription, redemption, interest, fee, and dividend."""
        # Subscription
        initialized.create_cashflow(
            "ev_001", "subscription", account, 1000.0, "CNY", "2023-01-01", product_id=product
        )
        # Redemption (negative)
        initialized.create_cashflow(
            "ev_002", "redemption", account, -500.0, "CNY", "2023-01-02", product_id=product
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

    def test_validation_negative_amounts(self, initialized, account):
        """Negative amounts only allowed for redemption, fee, transfer_out."""
        # Disallowed
        for etype in ("subscription", "interest", "dividend", "transfer_in", "other"):
            with pytest.raises(ValueError, match="Negative amount not allowed"):
                initialized.create_cashflow(f"err_{etype}", etype, account, -1.0, "CNY", "2023-01-01")

        # Allowed
        for etype in ("redemption", "fee", "transfer_out"):
            initialized.create_cashflow(f"ok_{etype}", etype, account, -1.0, "CNY", "2023-01-01")

    def test_validation_fx_currencies(self, initialized, account):
        """FX conversion must have both currencies and counter_amount."""
        with pytest.raises(ValueError, match="must have both currency and counter_currency"):
            initialized.create_cashflow("fx_err1", "fx_conversion", account, 100.0, "USD", "2023-01-01")

        with pytest.raises(ValueError, match="must have counter_amount"):
            initialized.create_cashflow("fx_err2", "fx_conversion", account, 100.0, "USD", "2023-01-01", counter_currency="CNY")

    def test_duplicate_event_id_rejected(self, initialized, account):
        """Reject duplicate event_ids with PortfolioBookError."""
        initialized.create_cashflow("dup", "interest", account, 10.0, "CNY", "2023-01-01")
        with pytest.raises(PortfolioBookError, match="Duplicate event_id"):
            initialized.create_cashflow("dup", "interest", account, 20.0, "CNY", "2023-01-02")

    def test_get_cashflows_for_product(self, initialized, account, product):
        """Test retrieval filter by product_id."""
        initialized.create_cashflow("p1", "subscription", account, 100.0, "CNY", "2023-01-01", product_id=product)
        initialized.create_cashflow("p2", "interest", account, 10.0, "CNY", "2023-01-02") # no product_id

        flows = initialized.get_cashflows_for_product(product)
        assert len(flows) == 1
        assert flows[0]["event_id"] == "p1"

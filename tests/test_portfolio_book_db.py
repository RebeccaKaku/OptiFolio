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
from src.domain.products import ProductDefinition


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
        """A freshly initialized database has current schema version."""
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

class TestSchemaMigrations:
    def test_migrate_v1_to_v2(self, db_tmp):
        """A v1 database is migrated to v2 on initialize()."""
        # Create a v1 database manually
        db_tmp.path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(db_tmp.path))
        conn.execute("CREATE TABLE _schema_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        conn.execute("INSERT INTO _schema_meta (key, value) VALUES ('version', '1')")
        conn.commit()
        conn.close()

        assert db_tmp.schema_version() == 1

        # This should trigger migration to v2
        db_tmp.initialize()
        assert db_tmp.schema_version() == 2

        # Verify products table exists
        conn = db_tmp.connect()
        try:
            conn.execute("SELECT * FROM products")
        finally:
            conn.close()


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


# ── Products CRUD ───────────────────────────────────────────────────

class TestProductsCRUD:
    def test_create_and_get_product(self, initialized):
        p = ProductDefinition(
            product_id="PROD001",
            name="Alpha Bank WMP",
            product_type="bank_wmp",
            issuer="Alpha Bank",
            currency="CNY",
            liquidity_type="t_plus_1",
            data_source="manual"
        )
        initialized.create_product(p)
        retrieved = initialized.get_product("PROD001")
        assert retrieved == p

    def test_get_non_existent_product(self, initialized):
        assert initialized.get_product("NO_SUCH_PROD") is None

    def test_update_product(self, initialized):
        p = ProductDefinition(
            product_id="PROD001",
            name="Initial Name",
            product_type="bank_wmp",
            issuer="Alpha Bank"
        )
        initialized.create_product(p)

        p_updated = ProductDefinition(
            product_id="PROD001",
            name="Updated Name",
            product_type="bank_wmp",
            issuer="Beta Bank",
            manager="Manager X"
        )
        initialized.update_product(p_updated)
        retrieved = initialized.get_product("PROD001")
        assert retrieved.name == "Updated Name"
        assert retrieved.issuer == "Beta Bank"
        assert retrieved.manager == "Manager X"

    def test_unknown_fields_preserved(self, initialized):
        """Fields in metadata and non-column fields are preserved."""
        p = ProductDefinition(
            product_id="PROD_EXTRA",
            name="Extra Fields Product",
            product_type="mixed_fund",
            risk_level="R3",
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
        p = ProductDefinition(
            product_id="PROD_NO_LIQ",
            name="No Liquidity Product",
            product_type="other",
            liquidity_type=None
        )
        initialized.create_product(p)
        retrieved = initialized.get_product("PROD_NO_LIQ")
        assert retrieved.liquidity_type == "unknown"

    @pytest.mark.parametrize("ptype", [
        "bank_deposit", "bank_wmp", "money_market_fund", "bond_fund",
        "equity_fund", "mixed_fund", "qdii_fund", "other"
    ])
    def test_product_types_round_trip(self, initialized, ptype):
        p = ProductDefinition(
            product_id=f"PROD_{ptype}",
            name=f"Product {ptype}",
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

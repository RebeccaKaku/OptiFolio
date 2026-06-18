"""Personal portfolio book database (local SQLite).

OptiFolio keeps personal data (accounts, products, snapshots, cashflows)
strictly separate from market data (FinData).  This module provides the
database foundation — a versioned, self-contained SQLite database that
lives in ``local/`` and is never committed to git.

Usage::

    db = PortfolioBookDatabase()          # does NOT create files
    db.initialize()                       # creates local/portfolio_book.sqlite
    conn = db.connect()                   # FK-enabled, row-factory set
    assert db.schema_version == 1
"""

from __future__ import annotations

import sqlite3
import logging
import json
from contextlib import closing
from pathlib import Path
from typing import Optional, Any, Dict, List, Callable

from src.core.paths import PROJECT_ROOT
from src.domain.products import ProductDefinition

_log = logging.getLogger(__name__)

# ── Exceptions ──────────────────────────────────────────────────────────────


class PortfolioBookError(Exception):
    """Base exception for portfolio book database errors."""


class UnsupportedSchemaVersionError(PortfolioBookError):
    """The on-disk schema version is newer than this code can handle."""


class InvalidSchemaMetadataError(PortfolioBookError):
    """The schema metadata table is missing or corrupt."""


# ── Database ────────────────────────────────────────────────────────────────


class PortfolioBookDatabase:
    """Versioned SQLite database for personal portfolio data.

    The database is NOT created on import or construction — only an
    explicit ``initialize()`` call creates the file and parent directory.

    Design principles:
    - Business tables (accounts, products, etc.) are added via migrations.
    - Schema version is stored in a ``_schema_meta`` metadata table.
    - Higher versions are rejected (no silent downgrade).
    - Connections always enable foreign keys and use ``sqlite3.Row``.
    """

    CURRENT_SCHEMA_VERSION: int = 3

    def __init__(self, path: Optional[str | Path] = None) -> None:
        if path is None:
            path = PROJECT_ROOT / "local" / "portfolio_book.sqlite"
        self._path: Path = Path(path)

    # ── Public API ──────────────────────────────────────────────────────

    def initialize(self) -> None:
        """Create the database file, parent directory, and metadata table.

        Idempotent — calling multiple times is safe.

        Raises:
            UnsupportedSchemaVersionError: if an existing database has a
                schema version higher than ``CURRENT_SCHEMA_VERSION``.
            InvalidSchemaMetadataError: if the metadata table is missing
                or its version cannot be read.
        """
        # Ensure parent directory exists
        self._path.parent.mkdir(parents=True, exist_ok=True)

        # Connect (creates file if absent), enable FK immediately
        conn = sqlite3.connect(str(self._path))
        conn.execute("PRAGMA foreign_keys = ON")

        try:
            # Create metadata table if absent
            conn.execute(
                "CREATE TABLE IF NOT EXISTS _schema_meta ("
                "  key   TEXT PRIMARY KEY,"
                "  value TEXT NOT NULL"
                ")"
            )

            cursor = conn.execute(
                "SELECT value FROM _schema_meta WHERE key = 'version'"
            )
            row = cursor.fetchone()

            if row is None:
                stored = 0
            else:
                stored = int(row[0])

            if stored > self.CURRENT_SCHEMA_VERSION:
                raise UnsupportedSchemaVersionError(
                    f"Database schema version {stored} is higher than "
                    f"this code supports ({self.CURRENT_SCHEMA_VERSION}). "
                    f"Upgrade OptiFolio or use a compatible database."
                )

            if stored < self.CURRENT_SCHEMA_VERSION:
                self._run_migrations(conn, stored, self.CURRENT_SCHEMA_VERSION)
                _log.info(
                    "PortfolioBookDatabase migrated from v%d to v%d at %s",
                    stored, self.CURRENT_SCHEMA_VERSION, self._path,
                )
            else:
                _log.debug(
                    "PortfolioBookDatabase already at v%d",
                    stored,
                )
        except ValueError as exc:
            raise InvalidSchemaMetadataError(
                f"Schema version in {self._path} is not a valid integer: {exc}"
            ) from exc
        except sqlite3.DatabaseError as exc:
            raise InvalidSchemaMetadataError(
                f"Failed to read schema metadata from {self._path}: {exc}"
            ) from exc
        finally:
            conn.close()

    def connect(self) -> sqlite3.Connection:
        """Return a connection with foreign keys enabled and row factory set.

        The caller is responsible for closing the connection.
        """
        conn = sqlite3.connect(str(self._path))
        conn.execute("PRAGMA foreign_keys = ON")
        conn.row_factory = sqlite3.Row
        return conn

    def schema_version(self) -> int:
        """Return the on-disk schema version.

        Raises:
            FileNotFoundError: if the database file does not exist.
            InvalidSchemaMetadataError: if the version cannot be read.
        """
        if not self._path.exists():
            raise FileNotFoundError(
                f"Portfolio book database not found at {self._path}. "
                f"Call initialize() first."
            )

        conn = sqlite3.connect(str(self._path))
        try:
            cursor = conn.execute(
                "SELECT value FROM _schema_meta WHERE key = 'version'"
            )
            row = cursor.fetchone()
            if row is None:
                raise InvalidSchemaMetadataError(
                    f"No schema version found in {self._path}. "
                    f"The _schema_meta table may be corrupted."
                )
            return int(row[0])
        except ValueError as exc:
            raise InvalidSchemaMetadataError(
                f"Schema version in {self._path} is not a valid integer: {exc}"
            ) from exc
        except sqlite3.DatabaseError as exc:
            raise InvalidSchemaMetadataError(
                f"Failed to read schema metadata from {self._path}: {exc}"
            ) from exc
        finally:
            conn.close()

    # ── Migrations ──────────────────────────────────────────────────────

    def _run_migrations(self, conn: sqlite3.Connection, from_v: int, to_v: int) -> None:
        """Sequential migration runner."""
        migrations: Dict[int, Callable[[sqlite3.Connection], None]] = {
            1: self._migrate_v1,
            2: self._migrate_v2,
        }

        for v in range(from_v + 1, to_v + 1):
            if v in migrations:
                _log.info("Running migration to v%d", v)
                migrations[v](conn)
            conn.execute(
                "INSERT OR REPLACE INTO _schema_meta (key, value) VALUES ('version', ?)",
                (str(v),),
            )
            conn.commit()

    def _migrate_v1(self, conn: sqlite3.Connection) -> None:
        """Create accounts table."""
        conn.execute(
            "CREATE TABLE IF NOT EXISTS accounts ("
            "    account_id   TEXT PRIMARY KEY,"
            "    name         TEXT NOT NULL,"
            "    institution  TEXT NOT NULL DEFAULT '',"
            "    account_type TEXT NOT NULL DEFAULT 'brokerage',"
            "    base_currency TEXT NOT NULL DEFAULT 'CNY',"
            "    ownership_scope TEXT NOT NULL DEFAULT 'personal',"
            "    status       TEXT NOT NULL DEFAULT 'active',"
            "    notes        TEXT NOT NULL DEFAULT '',"
            "    created_at   TEXT NOT NULL DEFAULT (datetime('now')),"
            "    updated_at   TEXT NOT NULL DEFAULT (datetime('now'))"
            ")"
        )

    def _migrate_v2(self, conn: sqlite3.Connection) -> None:
        """Create products table."""
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS products (
                product_id   TEXT PRIMARY KEY,
                name         TEXT NOT NULL,
                issuer       TEXT NOT NULL DEFAULT "",
                product_type TEXT NOT NULL DEFAULT "bank_wmp",
                currency     TEXT NOT NULL DEFAULT "CNY",
                liquidity    TEXT NOT NULL DEFAULT "t_plus_1",
                data_source  TEXT NOT NULL DEFAULT "manual",
                isin         TEXT NOT NULL DEFAULT "",
                notes        TEXT NOT NULL DEFAULT "",
                extra_json   TEXT NOT NULL DEFAULT "{}",
                created_at   TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at   TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

    # ── Products CRUD ───────────────────────────────────────────────────

    def create_product(self, product: ProductDefinition) -> None:
        """Persist a new product definition."""
        sql = """
            INSERT INTO products (
                product_id, name, issuer, product_type, currency,
                liquidity, data_source, isin, notes, extra_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        data = self._to_row(product)
        conn = self.connect()
        try:
            conn.execute(sql, data)
            conn.commit()
        finally:
            conn.close()

    def get_product(self, product_id: str) -> Optional[ProductDefinition]:
        """Fetch a product by its canonical ID."""
        conn = self.connect()
        try:
            row = conn.execute(
                "SELECT * FROM products WHERE product_id = ?", (product_id,)
            ).fetchone()
            if row is None:
                return None
            return self._from_row(row)
        finally:
            conn.close()

    def update_product(self, product: ProductDefinition) -> None:
        """Update an existing product definition."""
        sql = """
            UPDATE products SET
                name = ?, issuer = ?, product_type = ?, currency = ?,
                liquidity = ?, data_source = ?, isin = ?, notes = ?,
                extra_json = ?, updated_at = datetime("now")
            WHERE product_id = ?
        """
        # _to_row returns (product_id, name, issuer, type, cur, liq, src, isin, notes, extra)
        # We need name, issuer, type, cur, liq, src, isin, notes, extra, product_id
        row_data = self._to_row(product)
        update_data = list(row_data[1:]) + [row_data[0]]
        conn = self.connect()
        try:
            conn.execute(sql, update_data)
            conn.commit()
        finally:
            conn.close()

    def _to_row(self, p: ProductDefinition) -> tuple:
        """Convert ProductDefinition to database row tuple."""
        # Map fields
        liquidity = p.liquidity_type or "unknown"
        # Extract metadata and any other fields not in the table
        known_cols = {
            "product_id", "name", "issuer", "product_type", "currency",
            "liquidity_type", "data_source", "isin", "notes"
        }
        # In SQL it's 'liquidity', in ProductDefinition it's 'liquidity_type'

        extra = dict(p.metadata)
        # Capture fields from ProductDefinition that are NOT in the table
        # ProductDefinition: product_id, name, product_type, issuer, manager, currency,
        # risk_level, liquidity_type, fee_policy_id, benchmark_id, primary_instrument_id,
        # data_source, metadata

        if p.manager: extra["manager"] = p.manager
        if p.risk_level: extra["risk_level"] = p.risk_level
        if p.fee_policy_id: extra["fee_policy_id"] = p.fee_policy_id
        if p.benchmark_id: extra["benchmark_id"] = p.benchmark_id
        if p.primary_instrument_id: extra["primary_instrument_id"] = p.primary_instrument_id

        # We also need to handle isin and notes which might be in metadata or added to ProductDefinition?
        # Let's check ProductDefinition again.
        # It DOES NOT have isin or notes.
        # But the SQL table wants them.
        # So I should probably check metadata for them or they are just empty.
        isin = extra.pop("isin", "")
        notes = extra.pop("notes", "")

        return (
            p.product_id,
            p.name,
            p.issuer or "",
            p.product_type,
            p.currency,
            liquidity,
            p.data_source,
            isin,
            notes,
            json.dumps(extra)
        )

    def _from_row(self, row: sqlite3.Row) -> ProductDefinition:
        """Convert database row to ProductDefinition."""
        extra = json.loads(row["extra_json"])

        # Restore fields from extra if they exist
        manager = extra.pop("manager", None)
        risk_level = extra.pop("risk_level", None)
        fee_policy_id = extra.pop("fee_policy_id", None)
        benchmark_id = extra.pop("benchmark_id", None)
        primary_instrument_id = extra.pop("primary_instrument_id", None)

        # isin and notes were in the table, put them back into metadata if they were there?
        # Or should they just stay in the table?
        # Requirement: "Unknown fields preserved on round-trip"
        # Since isin and notes are in the table but NOT in ProductDefinition dataclass,
        # we should probably put them in metadata so they are not lost.
        if row["isin"]: extra["isin"] = row["isin"]
        if row["notes"]: extra["notes"] = row["notes"]

        return ProductDefinition(
            product_id=row["product_id"],
            name=row["name"],
            product_type=row["product_type"],
            issuer=row["issuer"],
            manager=manager,
            currency=row["currency"],
            risk_level=risk_level,
            liquidity_type=row["liquidity"],
            fee_policy_id=fee_policy_id,
            benchmark_id=benchmark_id,
            primary_instrument_id=primary_instrument_id,
            data_source=row["data_source"],
            metadata=extra
        )

    # ── Accounts CRUD ───────────────────────────────────────────────────

    def create_account(
        self, account_id: str, name: str, institution: str = "",
        account_type: str = "brokerage", base_currency: str = "CNY",
        ownership_scope: str = "personal", notes: str = "",
    ) -> None:
        if ownership_scope not in ("personal", "joint"):
            raise ValueError(
                f"Invalid ownership_scope: {ownership_scope}. Must be 'personal' or 'joint'."
            )
        with closing(self.connect()) as conn:
            with conn:
                conn.execute(
                    "INSERT INTO accounts (account_id, name, institution, "
                    "  account_type, base_currency, ownership_scope, notes) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (account_id, name, institution, account_type,
                     base_currency, ownership_scope, notes),
                )

    def get_account(self, account_id: str) -> Optional[sqlite3.Row]:
        with closing(self.connect()) as conn:
            return conn.execute(
                "SELECT * FROM accounts WHERE account_id = ?", (account_id,)
            ).fetchone()

    def update_account(self, account_id: str, **kwargs: Any) -> None:
        if "ownership_scope" in kwargs:
            if kwargs["ownership_scope"] not in ("personal", "joint"):
                raise ValueError("Invalid ownership_scope")
        if "status" in kwargs:
            if kwargs["status"] not in ("active", "inactive"):
                raise ValueError("Invalid status")
        if not kwargs:
            return
        fields = [f"{k} = ?" for k in kwargs]
        values = list(kwargs.values())
        fields.append("updated_at = (datetime('now'))")
        values.append(account_id)
        sql = f"UPDATE accounts SET {', '.join(fields)} WHERE account_id = ?"
        with closing(self.connect()) as conn:
            with conn:
                conn.execute(sql, tuple(values))

    def deactivate_account(self, account_id: str) -> None:
        self.update_account(account_id, status="inactive")

    # ── Backup & Restore ────────────────────────────────────────────────

    def backup(self, target_path: str | Path) -> Path:
        target = Path(target_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        source_conn = self.connect()
        dest_conn = sqlite3.connect(str(target))
        try:
            source_conn.backup(dest_conn)
            _log.info("Backup created at %s", target)
        finally:
            dest_conn.close()
            source_conn.close()
        return target

    def verify_backup(self, backup_path: str | Path) -> bool:
        path = Path(backup_path)
        if not path.exists():
            return False
        try:
            tmp_db = PortfolioBookDatabase(path=path)
            tmp_db.schema_version()
            return True
        except (PortfolioBookError, sqlite3.Error, FileNotFoundError):
            return False

    def restore_from(self, backup_path: str | Path, overwrite: bool = False) -> None:
        backup_path = Path(backup_path)
        if not self.verify_backup(backup_path):
            raise PortfolioBookError(f"Invalid backup file: {backup_path}")
        if self._path.exists() and not overwrite:
            raise FileExistsError(
                f"Database already exists at {self._path}. "
                f"Use overwrite=True to restore anyway."
            )
        backup_db = PortfolioBookDatabase(path=backup_path)
        backup_version = backup_db.schema_version()
        if backup_version > self.CURRENT_SCHEMA_VERSION:
            raise UnsupportedSchemaVersionError(
                f"Backup version {backup_version} is higher than "
                f"this code supports ({self.CURRENT_SCHEMA_VERSION})."
            )
        self._path.parent.mkdir(parents=True, exist_ok=True)
        dest_conn = sqlite3.connect(str(self._path))
        source_conn = sqlite3.connect(str(backup_path))
        try:
            source_conn.backup(dest_conn)
            _log.info("Database restored from %s", backup_path)
        finally:
            source_conn.close()
            dest_conn.close()

    @property
    def path(self) -> Path:
        """The resolved database file path (read-only)."""
        return self._path

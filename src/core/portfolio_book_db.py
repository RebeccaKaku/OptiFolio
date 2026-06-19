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

    CURRENT_SCHEMA_VERSION: int = 9
    _ACCOUNT_UPDATE_FIELDS = frozenset(
        {
            "name",
            "institution",
            "account_type",
            "base_currency",
            "ownership_scope",
            "status",
            "notes",
        }
    )

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
            3: self._migrate_v3,
            4: self._migrate_v4,
            5: self._migrate_v5,
            6: self._migrate_v6,
            7: self._migrate_v7,
            8: self._migrate_v8,
            9: self._migrate_v9,
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

    def _migrate_v9(self, conn: sqlite3.Connection) -> None:
        """Create exposure_batches and product_exposures tables."""
        conn.execute(
            """
            CREATE TABLE exposure_batches (
                exposure_batch_id TEXT PRIMARY KEY,
                product_id        TEXT NOT NULL,
                as_of             TEXT NOT NULL,
                known_at          TEXT NOT NULL,
                source            TEXT NOT NULL DEFAULT 'manual',
                quality           TEXT NOT NULL DEFAULT 'reported' CHECK (quality IN ('reported', 'estimated', 'stale', 'unknown')),
                status            TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'confirmed', 'superseded')),
                notes             TEXT,
                created_at        TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at        TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (product_id) REFERENCES products (product_id)
            )
            """
        )
        conn.execute("CREATE INDEX idx_exposure_batches_product_as_of ON exposure_batches (product_id, as_of)")
        conn.execute("CREATE INDEX idx_exposure_batches_status ON exposure_batches (status)")

        conn.execute(
            """
            CREATE TABLE product_exposures (
                exposure_batch_id TEXT NOT NULL,
                dimension         TEXT NOT NULL,
                bucket            TEXT NOT NULL,
                weight_ppm        INTEGER NOT NULL CHECK (weight_ppm >= 0 AND weight_ppm <= 1000000),
                method            TEXT NOT NULL DEFAULT 'actual' CHECK (method IN ('actual', 'reported', 'estimated', 'proxy', 'unknown')),
                source_ref        TEXT,
                notes             TEXT,
                PRIMARY KEY (exposure_batch_id, dimension, bucket),
                FOREIGN KEY (exposure_batch_id) REFERENCES exposure_batches (exposure_batch_id) ON DELETE CASCADE
            )
            """
        )

    def _migrate_v8(self, conn: sqlite3.Connection) -> None:
        """Create import_drafts and import_candidates tables."""
        conn.execute(
            """
            CREATE TABLE import_drafts (
                import_id        TEXT PRIMARY KEY,
                contract_version INTEGER NOT NULL,
                target_kind      TEXT NOT NULL CHECK (target_kind IN ('account', 'product', 'position')),
                source_type      TEXT NOT NULL,
                source_ref       TEXT NOT NULL,
                status           TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'reviewed', 'applied', 'rejected')),
                created_at       TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at       TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute("CREATE INDEX idx_import_drafts_status ON import_drafts (status)")

        conn.execute(
            """
            CREATE TABLE import_candidates (
                candidate_id         TEXT PRIMARY KEY,
                import_id            TEXT NOT NULL,
                field_name           TEXT NOT NULL,
                raw_text             TEXT,
                proposed_value_json  TEXT,
                confidence           REAL CHECK (confidence IS NULL OR (confidence >= 0 AND confidence <= 1)),
                review_status        TEXT NOT NULL DEFAULT 'unreviewed' CHECK (review_status IN ('unreviewed', 'accepted', 'corrected', 'rejected')),
                corrected_value_json TEXT,
                notes                TEXT,
                FOREIGN KEY (import_id) REFERENCES import_drafts (import_id) ON DELETE CASCADE
            )
            """
        )
        conn.execute("CREATE INDEX idx_import_candidates_import_id ON import_candidates (import_id)")

    def _migrate_v7(self, conn: sqlite3.Connection) -> None:
        """Rebuild cashflow_events with financial semantics and FKs."""
        # 1. Create new table with strict constraints
        conn.execute(
            """
            CREATE TABLE cashflow_events_v7 (
                event_id        TEXT PRIMARY KEY,
                event_type      TEXT NOT NULL,
                account_id      TEXT NOT NULL,
                product_id      TEXT,
                amount          REAL NOT NULL,
                currency        TEXT NOT NULL,
                counter_amount  REAL,
                counter_currency TEXT,
                pair_event_id   TEXT,
                effective_date  TEXT NOT NULL,
                source          TEXT DEFAULT 'manual',
                notes           TEXT,
                created_at      TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at      TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (account_id) REFERENCES accounts (account_id),
                FOREIGN KEY (product_id) REFERENCES products (product_id),
                CHECK (amount <> 0),
                CHECK (
                    (event_type IN ('external_contribution', 'sale', 'interest', 'dividend', 'transfer_in', 'maturity') AND amount > 0) OR
                    (event_type IN ('external_withdrawal', 'purchase', 'fee', 'tax', 'transfer_out') AND amount < 0) OR
                    (event_type = 'fx_conversion' AND amount < 0 AND counter_amount IS NOT NULL AND counter_amount > 0 AND counter_currency IS NOT NULL AND currency <> counter_currency) OR
                    (event_type = 'other' AND notes IS NOT NULL AND notes <> '')
                )
            )
            """
        )

        # 2. Migrate data with semantic remapping and sign correction
        conn.execute(
            """
            INSERT INTO cashflow_events_v7 (
                event_id, event_type, account_id, product_id, amount, currency,
                counter_amount, counter_currency, pair_event_id, effective_date,
                source, notes, created_at, updated_at
            )
            SELECT
                event_id,
                CASE
                    WHEN event_type = 'subscription' THEN 'purchase'
                    WHEN event_type = 'redemption' THEN 'sale'
                    ELSE event_type
                END as event_type,
                account_id,
                product_id,
                CASE
                    WHEN event_type = 'subscription' THEN -abs(amount)
                    WHEN event_type = 'redemption' THEN abs(amount)
                    ELSE amount
                END as amount,
                currency,
                counter_amount,
                counter_currency,
                pair_event_id,
                effective_date,
                source,
                CASE
                    WHEN event_type = 'other' AND (notes IS NULL OR notes = '') THEN 'Migrated from v6'
                    ELSE notes
                END as notes,
                created_at,
                updated_at
            FROM cashflow_events
            WHERE (
                (event_type IN ('interest', 'dividend', 'transfer_in') AND amount > 0) OR
                (event_type IN ('fee', 'transfer_out') AND amount < 0) OR
                (event_type = 'fx_conversion' AND amount < 0 AND counter_amount > 0 AND counter_currency IS NOT NULL AND currency <> counter_currency) OR
                (event_type IN ('subscription', 'redemption', 'other'))
            )
            """
        )

        # 3. Swap tables
        conn.execute("DROP TABLE cashflow_events")
        conn.execute("ALTER TABLE cashflow_events_v7 RENAME TO cashflow_events")

    def _migrate_v3(self, conn: sqlite3.Connection) -> None:
        """Create snapshot_batches and position_snapshots tables."""
        conn.execute(
            "CREATE TABLE IF NOT EXISTS snapshot_batches ("
            "    batch_id   TEXT PRIMARY KEY,"
            "    status     TEXT NOT NULL DEFAULT 'draft',"
            "    as_of      TEXT NOT NULL,"
            "    source     TEXT DEFAULT 'manual',"
            "    quality    TEXT DEFAULT 'reported',"
            "    notes      TEXT,"
            "    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,"
            "    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP"
            ")"
        )
        conn.execute(
            "CREATE TABLE IF NOT EXISTS position_snapshots ("
            "    snapshot_id   INTEGER PRIMARY KEY AUTOINCREMENT,"
            "    batch_id      TEXT NOT NULL,"
            "    account_id    TEXT NOT NULL,"
            "    product_id    TEXT NOT NULL,"
            "    quantity      REAL NOT NULL,"
            "    market_value  REAL,"
            "    cost_basis    REAL,"
            "    currency      TEXT DEFAULT 'CNY',"
            "    source        TEXT,"
            "    quality       TEXT,"
            "    notes         TEXT,"
            "    UNIQUE(batch_id, account_id, product_id),"
            "    FOREIGN KEY (batch_id) REFERENCES snapshot_batches(batch_id),"
            "    FOREIGN KEY (account_id) REFERENCES accounts(account_id),"
            "    FOREIGN KEY (product_id) REFERENCES products(product_id)"
            ")"
        )

    def _migrate_v5(self, conn: sqlite3.Connection) -> None:
        """Merge marker — no structural change.

        v5 was the merge of snapshot (v3) and cashflow (v4) branches.
        No DDL is executed; this migration exists so the version trail
        is explicit and future maintainers can see that v5 is intentional.
        """

    def _migrate_v6(self, conn: sqlite3.Connection) -> None:
        """Add snapshot_batch_accounts coverage table; make quantity nullable.

        1. Create ``snapshot_batch_accounts`` to record per-account coverage
           (complete / partial / empty) within each snapshot batch.
        2. Rebuild ``position_snapshots`` so ``quantity`` is NULL-able,
           preserving all existing data, unique constraints, and foreign keys.
        """
        # 1. Batch–account coverage table
        conn.execute(
            "CREATE TABLE IF NOT EXISTS snapshot_batch_accounts ("
            "    batch_id   TEXT NOT NULL,"
            "    account_id TEXT NOT NULL,"
            "    coverage   TEXT NOT NULL CHECK "
            "        (coverage IN ('complete', 'partial', 'empty')),"
            "    notes      TEXT,"
            "    PRIMARY KEY (batch_id, account_id),"
            "    FOREIGN KEY (batch_id) REFERENCES snapshot_batches(batch_id),"
            "    FOREIGN KEY (account_id) REFERENCES accounts(account_id)"
            ")"
        )

        # 2. Rebuild position_snapshots with nullable quantity
        conn.execute(
            "CREATE TABLE position_snapshots_v6 ("
            "    snapshot_id   INTEGER PRIMARY KEY AUTOINCREMENT,"
            "    batch_id      TEXT NOT NULL,"
            "    account_id    TEXT NOT NULL,"
            "    product_id    TEXT NOT NULL,"
            "    quantity      REAL,"
            "    market_value  REAL,"
            "    cost_basis    REAL,"
            "    currency      TEXT DEFAULT 'CNY',"
            "    source        TEXT,"
            "    quality       TEXT,"
            "    notes         TEXT,"
            "    UNIQUE(batch_id, account_id, product_id),"
            "    FOREIGN KEY (batch_id) REFERENCES snapshot_batches(batch_id),"
            "    FOREIGN KEY (account_id) REFERENCES accounts(account_id),"
            "    FOREIGN KEY (product_id) REFERENCES products(product_id)"
            ")"
        )
        conn.execute(
            "INSERT INTO position_snapshots_v6 SELECT * FROM position_snapshots"
        )
        # Existing v5 snapshots did not record whether an account was fully
        # captured. Preserve that uncertainty instead of silently treating
        # historical batches as complete.
        conn.execute(
            "INSERT OR IGNORE INTO snapshot_batch_accounts "
            "(batch_id, account_id, coverage, notes) "
            "SELECT DISTINCT batch_id, account_id, 'partial', "
            "'Backfilled from pre-v6 snapshot; completeness unknown' "
            "FROM position_snapshots"
        )
        conn.execute("DROP TABLE position_snapshots")
        conn.execute(
            "ALTER TABLE position_snapshots_v6 RENAME TO position_snapshots"
        )

    def _migrate_v4(self, conn: sqlite3.Connection) -> None:
        """Create cashflow_events table."""
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS cashflow_events (
                event_id        TEXT PRIMARY KEY,
                event_type      TEXT NOT NULL,
                account_id      TEXT NOT NULL,
                product_id      TEXT,
                amount          REAL NOT NULL,
                currency        TEXT NOT NULL,
                counter_amount  REAL,
                counter_currency TEXT,
                pair_event_id   TEXT,
                effective_date  TEXT NOT NULL,
                source          TEXT DEFAULT 'manual',
                notes           TEXT,
                created_at      TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at      TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (account_id) REFERENCES accounts (account_id)
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

    def list_products(self) -> List[ProductDefinition]:
        """List all products ordered by name then product_id."""
        conn = self.connect()
        try:
            rows = conn.execute(
                "SELECT * FROM products ORDER BY name, product_id"
            ).fetchall()
            return [self._from_row(row) for row in rows]
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
        if not account_id or not account_id.strip():
            raise ValueError("account_id must not be empty")
        if not name or not name.strip():
            raise ValueError("name must not be empty")
        if len(base_currency) != 3 or not base_currency.isalpha():
            raise ValueError("base_currency must be a 3-letter currency code")
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
        unknown_fields = set(kwargs) - self._ACCOUNT_UPDATE_FIELDS
        if unknown_fields:
            names = ", ".join(sorted(unknown_fields))
            raise ValueError(f"Unsupported account update fields: {names}")
        if "name" in kwargs and (
            not isinstance(kwargs["name"], str) or not kwargs["name"].strip()
        ):
            raise ValueError("name must not be empty")
        if "base_currency" in kwargs:
            currency = kwargs["base_currency"]
            if (
                not isinstance(currency, str)
                or len(currency) != 3
                or not currency.isalpha()
            ):
                raise ValueError("base_currency must be a 3-letter currency code")
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
                cursor = conn.execute(sql, tuple(values))
                if cursor.rowcount == 0:
                    raise PortfolioBookError(f"Account {account_id} not found")

    def deactivate_account(self, account_id: str) -> None:
        self.update_account(account_id, status="inactive")

    def list_accounts(self, status: str = "active") -> List[sqlite3.Row]:
        """List accounts, optionally filtered by status.

        Args:
            status: ``"active"``, ``"inactive"``, or ``"all"``.

        Returns:
            List of sqlite3.Row ordered by name then account_id.
        """
        with closing(self.connect()) as conn:
            if status == "all":
                return conn.execute(
                    "SELECT * FROM accounts ORDER BY name, account_id"
                ).fetchall()
            if status not in ("active", "inactive"):
                raise ValueError(
                    f"status must be 'active', 'inactive', or 'all', got {status!r}"
                )
            return conn.execute(
                "SELECT * FROM accounts WHERE status = ? ORDER BY name, account_id",
                (status,),
            ).fetchall()

    # ── Snapshots CRUD ──────────────────────────────────────────────────

    def create_snapshot_batch(
        self, batch_id: str, as_of: str, source: str = 'manual',
        quality: str = 'reported', notes: Optional[str] = None
    ) -> None:
        with closing(self.connect()) as conn:
            with conn:
                conn.execute(
                    "INSERT INTO snapshot_batches (batch_id, as_of, source, quality, notes) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (batch_id, as_of, source, quality, notes)
                )

    def add_snapshot(
        self, batch_id: str, account_id: str, product_id: str,
        quantity: Optional[float] = None,
        market_value: Optional[float] = None,
        cost_basis: Optional[float] = None, currency: str = 'CNY',
        source: Optional[str] = None, quality: Optional[str] = None,
        notes: Optional[str] = None
    ) -> None:
        # --- value validation ---
        if quantity is None and market_value is None:
            raise ValueError(
                "At least one of quantity or market_value must be provided"
            )
        if quantity is not None and quantity < 0:
            raise ValueError("quantity must not be negative")
        if market_value is not None and market_value < 0:
            raise ValueError("market_value must not be negative")
        if cost_basis is not None and cost_basis < 0:
            raise ValueError("cost_basis must not be negative")

        with closing(self.connect()) as conn:
            with conn:
                batch = conn.execute(
                    "SELECT status FROM snapshot_batches WHERE batch_id = ?",
                    (batch_id,)
                ).fetchone()
                if not batch:
                    raise PortfolioBookError(f"Batch {batch_id} not found")
                if batch["status"] != "draft":
                    raise PortfolioBookError(
                        f"Cannot add to {batch['status']} batch {batch_id}"
                    )

                # --- coverage check ---
                cov_row = conn.execute(
                    "SELECT coverage FROM snapshot_batch_accounts "
                    "WHERE batch_id = ? AND account_id = ?",
                    (batch_id, account_id),
                ).fetchone()
                if cov_row is None:
                    raise PortfolioBookError(
                        f"Account {account_id} is not registered in batch "
                        f"{batch_id} coverage. Call set_batch_account_coverage() first."
                    )
                if cov_row["coverage"] == "empty":
                    raise PortfolioBookError(
                        f"Account {account_id} is marked as 'empty' in batch "
                        f"{batch_id} — cannot add positions."
                    )

                conn.execute(
                    "INSERT INTO position_snapshots (batch_id, account_id, product_id, "
                    "quantity, market_value, cost_basis, currency, source, quality, notes) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (batch_id, account_id, product_id, quantity, market_value,
                     cost_basis, currency, source, quality, notes)
                )

    def set_batch_account_coverage(
        self, batch_id: str, account_id: str, coverage: str,
        notes: Optional[str] = None,
    ) -> None:
        """Register or update an account's coverage within a snapshot batch.

        *coverage* must be ``"complete"``, ``"partial"``, or ``"empty"``.
        Only **draft** batches accept coverage changes.
        """
        valid = {"complete", "partial", "empty"}
        if coverage not in valid:
            raise ValueError(
                f"coverage must be one of {sorted(valid)}, got {coverage!r}"
            )

        with closing(self.connect()) as conn:
            with conn:
                batch = conn.execute(
                    "SELECT status FROM snapshot_batches WHERE batch_id = ?",
                    (batch_id,),
                ).fetchone()
                if batch is None:
                    raise PortfolioBookError(f"Batch {batch_id} not found")
                if batch["status"] != "draft":
                    raise PortfolioBookError(
                        f"Cannot modify coverage for {batch['status']} batch {batch_id}"
                    )

                if coverage == "empty":
                    position_count = conn.execute(
                        "SELECT COUNT(*) FROM position_snapshots "
                        "WHERE batch_id = ? AND account_id = ?",
                        (batch_id, account_id),
                    ).fetchone()[0]
                    if position_count:
                        raise PortfolioBookError(
                            f"Account {account_id} has positions in batch {batch_id} "
                            "and cannot be marked empty"
                        )

                conn.execute(
                    "INSERT INTO snapshot_batch_accounts "
                    "(batch_id, account_id, coverage, notes) VALUES (?, ?, ?, ?) "
                    "ON CONFLICT(batch_id, account_id) DO UPDATE SET "
                    "coverage = excluded.coverage, notes = excluded.notes",
                    (batch_id, account_id, coverage, notes),
                )

    def confirm_batch(self, batch_id: str) -> None:
        with closing(self.connect()) as conn:
            with conn:
                batch = conn.execute(
                    "SELECT status FROM snapshot_batches WHERE batch_id = ?",
                    (batch_id,),
                ).fetchone()
                if batch is None:
                    raise PortfolioBookError(f"Batch {batch_id} not found")
                if batch["status"] != "draft":
                    raise PortfolioBookError(
                        f"Batch {batch_id} is already {batch['status']}"
                    )

                # At least one account must be registered in coverage
                cov_count = conn.execute(
                    "SELECT COUNT(*) FROM snapshot_batch_accounts "
                    "WHERE batch_id = ?",
                    (batch_id,),
                ).fetchone()[0]
                if cov_count == 0:
                    raise PortfolioBookError(
                        f"Batch {batch_id} has no accounts registered in "
                        f"coverage. Call set_batch_account_coverage() first."
                    )

                cursor = conn.execute(
                    "UPDATE snapshot_batches SET status = 'confirmed', "
                    "updated_at = CURRENT_TIMESTAMP WHERE batch_id = ? AND status = 'draft'",
                    (batch_id,)
                )
                if cursor.rowcount == 0:
                    raise PortfolioBookError(f"Batch {batch_id} not found")

    def supersede_batch(self, batch_id: str) -> None:
        with closing(self.connect()) as conn:
            with conn:
                cursor = conn.execute(
                    "UPDATE snapshot_batches SET status = 'superseded', "
                    "updated_at = CURRENT_TIMESTAMP WHERE batch_id = ?",
                    (batch_id,)
                )
                if cursor.rowcount == 0:
                    raise PortfolioBookError(f"Batch {batch_id} not found")

    def get_batch(self, batch_id: str) -> Optional[Dict[str, Any]]:
        with closing(self.connect()) as conn:
            batch_row = conn.execute(
                "SELECT * FROM snapshot_batches WHERE batch_id = ?", (batch_id,)
            ).fetchone()
            if not batch_row:
                return None
            batch = dict(batch_row)
            snapshot_rows = conn.execute(
                "SELECT * FROM position_snapshots WHERE batch_id = ?", (batch_id,)
            ).fetchall()
            batch["snapshots"] = [dict(row) for row in snapshot_rows]
            # Include account coverage
            coverage_rows = conn.execute(
                "SELECT account_id, coverage, notes "
                "FROM snapshot_batch_accounts WHERE batch_id = ?",
                (batch_id,),
            ).fetchall()
            batch["account_coverage"] = [dict(row) for row in coverage_rows]
            return batch

    def get_latest_confirmed_batch(self, as_of: str) -> Optional[Dict[str, Any]]:
        """Return the most recent confirmed batch on or before as_of date."""
        with closing(self.connect()) as conn:
            row = conn.execute(
                "SELECT batch_id FROM snapshot_batches "
                "WHERE status = 'confirmed' AND as_of <= ? "
                "ORDER BY as_of DESC, created_at DESC LIMIT 1",
                (as_of,)
            ).fetchone()
            if not row:
                return None
            return self.get_batch(row["batch_id"])

    def get_previous_confirmed_batch(self, as_of: str) -> Optional[Dict[str, Any]]:
        """Return the confirmed batch immediately preceding as_of date."""
        with closing(self.connect()) as conn:
            row = conn.execute(
                "SELECT batch_id FROM snapshot_batches "
                "WHERE status = 'confirmed' AND as_of < ? "
                "ORDER BY as_of DESC, created_at DESC LIMIT 1",
                (as_of,)
            ).fetchone()
            if not row:
                return None
            return self.get_batch(row["batch_id"])

    def get_batch_progress(self, batch_id: str) -> Dict[str, Any]:
        """Return batch progress including per-account coverage and completeness.

        ``is_complete`` is True only when **every** registered account has
        coverage ``"complete"`` or ``"empty"``.
        """
        batch = self.get_batch(batch_id)
        if batch is None:
            raise PortfolioBookError(f"Batch {batch_id} not found")

        coverages = batch.get("account_coverage", [])
        is_complete = (
            len(coverages) > 0
            and all(c["coverage"] in ("complete", "empty") for c in coverages)
        )
        return {
            "batch_id": batch["batch_id"],
            "status": batch["status"],
            "as_of": batch["as_of"],
            "accounts": coverages,
            "is_complete": is_complete,
        }

    # ── Cashflow CRUD ───────────────────────────────────────────────────

    def create_cashflow(
        self,
        event_id: str,
        event_type: str,
        account_id: str,
        amount: float,
        currency: str,
        effective_date: str,
        product_id: Optional[str] = None,
        counter_amount: Optional[float] = None,
        counter_currency: Optional[str] = None,
        pair_event_id: Optional[str] = None,
        source: str = "manual",
        notes: Optional[str] = None,
    ) -> None:
        """Record a new cashflow event with strict financial semantics."""
        valid_types = {
            "external_contribution", "external_withdrawal", "purchase", "sale",
            "interest", "dividend", "fee", "tax", "transfer_in", "transfer_out",
            "fx_conversion", "maturity", "other"
        }
        if event_type not in valid_types:
            raise ValueError(f"Invalid event_type: {event_type}")

        if amount == 0:
            raise ValueError("Cashflow amount cannot be zero")

        positive_types = {"external_contribution", "sale", "interest", "dividend", "transfer_in", "maturity"}
        negative_types = {"external_withdrawal", "purchase", "fee", "tax", "transfer_out"}

        if event_type in positive_types and amount < 0:
            raise ValueError(f"{event_type} must have a positive amount")
        if event_type in negative_types and amount > 0:
            raise ValueError(f"{event_type} must have a negative amount")

        if event_type == "fx_conversion":
            if amount >= 0:
                raise ValueError("FX conversion primary amount must be negative")
            if not counter_currency or counter_amount is None or counter_amount <= 0:
                raise ValueError("FX conversion must have positive counter_amount and counter_currency")
            if currency == counter_currency:
                raise ValueError("FX conversion currencies must be different")

        if event_type == "other" and not (notes and notes.strip()):
            raise ValueError("Notes are required for 'other' event type")

        sql = """
            INSERT INTO cashflow_events (
                event_id, event_type, account_id, product_id, amount, currency,
                counter_amount, counter_currency, pair_event_id, effective_date,
                source, notes
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        params = (
            event_id, event_type, account_id, product_id, amount, currency,
            counter_amount, counter_currency, pair_event_id, effective_date,
            source, notes
        )
        with closing(self.connect()) as conn:
            try:
                with conn:
                    conn.execute(sql, params)
            except sqlite3.IntegrityError as exc:
                if "UNIQUE constraint failed: cashflow_events.event_id" in str(exc):
                    raise PortfolioBookError(f"Duplicate event_id: {event_id}") from exc
                raise

    def get_cashflows_for_account(self, account_id: str) -> List[sqlite3.Row]:
        """Retrieve all cashflow events for a specific account."""
        with closing(self.connect()) as conn:
            return conn.execute(
                "SELECT * FROM cashflow_events WHERE account_id = ? ORDER BY effective_date DESC",
                (account_id,)
            ).fetchall()

    def get_cashflows_for_product(self, product_id: str) -> List[sqlite3.Row]:
        """Retrieve all cashflow events for a specific product."""
        with closing(self.connect()) as conn:
            return conn.execute(
                "SELECT * FROM cashflow_events WHERE product_id = ? ORDER BY effective_date DESC",
                (product_id,)
            ).fetchall()

    def get_cashflows_for_period(self, start_date: str, end_date: str) -> List[sqlite3.Row]:
        """Retrieve all cashflow events in the range (start_date, end_date]."""
        with closing(self.connect()) as conn:
            return conn.execute(
                "SELECT * FROM cashflow_events "
                "WHERE effective_date > ? AND effective_date <= ? "
                "ORDER BY effective_date ASC",
                (start_date, end_date)
            ).fetchall()

    def link_transfer(self, event_a_id: str, event_b_id: str) -> None:
        """Link two transfer events (e.g., transfer_in and transfer_out).

        Hardened validation:
        - Both events must exist.
        - One must be 'transfer_in', the other 'transfer_out'.
        - Must have the same currency and same absolute amount.
        - Cannot link an event to itself.
        - Cannot link events that are already paired.
        - Atomic update in a single transaction.
        """
        if event_a_id == event_b_id:
            raise ValueError("Cannot link an event to itself")

        with closing(self.connect()) as conn:
            with conn:
                # Fetch both events
                row_a = conn.execute("SELECT * FROM cashflow_events WHERE event_id = ?", (event_a_id,)).fetchone()
                row_b = conn.execute("SELECT * FROM cashflow_events WHERE event_id = ?", (event_b_id,)).fetchone()

                if not row_a or not row_b:
                    raise PortfolioBookError("One or both transfer events not found")

                # Type validation
                types = {row_a["event_type"], row_b["event_type"]}
                if types != {"transfer_in", "transfer_out"}:
                    raise ValueError("Pair must consist of one 'transfer_in' and one 'transfer_out'")

                # Currency and Amount validation
                if row_a["currency"] != row_b["currency"]:
                    raise ValueError("Transfer pair must have the same currency")
                if abs(row_a["amount"]) != abs(row_b["amount"]):
                    raise ValueError("Transfer pair must have the same absolute amount")

                # Already paired check
                if row_a["pair_event_id"] or row_b["pair_event_id"]:
                    raise PortfolioBookError("One or both events are already paired")

                # Update both in the same transaction
                conn.execute(
                    "UPDATE cashflow_events SET pair_event_id = ?, updated_at = CURRENT_TIMESTAMP WHERE event_id = ?",
                    (event_b_id, event_a_id)
                )
                conn.execute(
                    "UPDATE cashflow_events SET pair_event_id = ?, updated_at = CURRENT_TIMESTAMP WHERE event_id = ?",
                    (event_a_id, event_b_id)
                )

    def classify_wealth_flow(self, event_type: str) -> str:
        """Classify a cashflow event type into a wealth flow category.

        Returns one of:
        - 'external_flow': Capital entering or leaving the portfolio.
        - 'investment_pnl': Direct gains or losses from investments.
        - 'internal': Asset allocation changes (buy/sell/fx/transfer).
        - 'unclassified': For 'other' or unknown types.
        """
        mapping = {
            "external_contribution": "external_flow",
            "external_withdrawal": "external_flow",
            "interest": "investment_pnl",
            "dividend": "investment_pnl",
            "fee": "investment_pnl",
            "tax": "investment_pnl",
            "purchase": "internal",
            "sale": "internal",
            "transfer_in": "internal",
            "transfer_out": "internal",
            "fx_conversion": "internal",
            "maturity": "internal",
            "other": "unclassified",
        }
        return mapping.get(event_type, "unclassified")

    # ── Product Exposures CRUD ──────────────────────────────────────────

    def create_exposure_batch(
        self, batch_id: str, product_id: str, as_of: str, known_at: str,
        source: str = 'manual', quality: str = 'reported', notes: Optional[str] = None
    ) -> None:
        """Create a new exposure batch for a product."""
        with closing(self.connect()) as conn:
            with conn:
                conn.execute(
                    """
                    INSERT INTO exposure_batches (
                        exposure_batch_id, product_id, as_of, known_at,
                        source, quality, notes
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (batch_id, product_id, as_of, known_at, source, quality, notes)
                )

    def add_product_exposure(
        self, batch_id: str, dimension: str, bucket: str, weight_ppm: int,
        method: str = 'actual', source_ref: Optional[str] = None,
        notes: Optional[str] = None
    ) -> None:
        """Add a single exposure component to a draft batch."""
        with closing(self.connect()) as conn:
            with conn:
                batch = conn.execute(
                    "SELECT status FROM exposure_batches WHERE exposure_batch_id = ?",
                    (batch_id,)
                ).fetchone()
                if not batch:
                    raise PortfolioBookError(f"Exposure batch {batch_id} not found")
                if batch["status"] != "draft":
                    raise PortfolioBookError(
                        f"Cannot add to {batch['status']} exposure batch {batch_id}"
                    )

                conn.execute(
                    """
                    INSERT INTO product_exposures (
                        exposure_batch_id, dimension, bucket, weight_ppm,
                        method, source_ref, notes
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (batch_id, dimension, bucket, weight_ppm, method, source_ref, notes)
                )

    def confirm_exposure_batch(self, batch_id: str) -> None:
        """Confirm an exposure batch."""
        with closing(self.connect()) as conn:
            with conn:
                batch = conn.execute(
                    "SELECT status FROM exposure_batches WHERE exposure_batch_id = ?",
                    (batch_id,)
                ).fetchone()
                if not batch:
                    raise PortfolioBookError(f"Exposure batch {batch_id} not found")
                if batch["status"] != "draft":
                    raise PortfolioBookError(f"Batch {batch_id} is already {batch['status']}")

                conn.execute(
                    "UPDATE exposure_batches SET status = 'confirmed', updated_at = CURRENT_TIMESTAMP "
                    "WHERE exposure_batch_id = ?",
                    (batch_id,)
                )

    def supersede_exposure_batch(self, batch_id: str) -> None:
        """Mark an exposure batch as superseded."""
        with closing(self.connect()) as conn:
            with conn:
                conn.execute(
                    "UPDATE exposure_batches SET status = 'superseded', updated_at = CURRENT_TIMESTAMP "
                    "WHERE exposure_batch_id = ?",
                    (batch_id,)
                )

    def get_exposure_batch(self, batch_id: str) -> Optional[Dict[str, Any]]:
        """Fetch an exposure batch with all its components and residuals."""
        with closing(self.connect()) as conn:
            batch_row = conn.execute(
                "SELECT * FROM exposure_batches WHERE exposure_batch_id = ?",
                (batch_id,)
            ).fetchone()
            if not batch_row:
                return None

            batch = dict(batch_row)
            exposure_rows = conn.execute(
                "SELECT * FROM product_exposures WHERE exposure_batch_id = ? "
                "ORDER BY dimension, weight_ppm DESC",
                (batch_id,)
            ).fetchall()

            exposures = [dict(row) for row in exposure_rows]
            batch["exposures"] = exposures

            # Calculate unknown residuals per dimension
            residuals = {}
            sums = {}
            for exp in exposures:
                dim = exp["dimension"]
                sums[dim] = sums.get(dim, 0) + exp["weight_ppm"]

            for dim, total in sums.items():
                if total > 1000000:
                     # This should have been caught by DB check constraint if individual weights were > 1M,
                     # but sum can still exceed 1M. Validation should happen in service layer.
                     pass
                if total < 1000000:
                    residuals[dim] = 1000000 - total

            batch["unknown_residuals"] = residuals
            return batch

    # ── Backup & Restore ────────────────────────────────────────────────

    def backup(self, target_path: str | Path, overwrite: bool = False) -> Path:
        """Create a backup of the current database.

        Args:
            target_path: Path to the backup file.
            overwrite: If True, overwrite the target file if it exists.

        Returns:
            The path to the backup file.

        Raises:
            PortfolioBookError: if the source is not initialized or verification fails.
            FileExistsError: if target exists and overwrite is False.
        """
        target = Path(target_path)

        # 1. Source must exist and be initialized
        # schema_version() raises FileNotFoundError if it doesn't exist,
        # or InvalidSchemaMetadataError if it's not initialized properly.
        self.schema_version()

        # 2. Source != Target
        if self._path.exists() and target.exists():
            if self._path.resolve() == target.resolve():
                raise PortfolioBookError("Source and target database paths are the same.")

        # 3. Target exists and overwrite=False
        if target.exists() and not overwrite:
            raise FileExistsError(
                f"Backup target already exists at {target}. Use overwrite=True."
            )

        target.parent.mkdir(parents=True, exist_ok=True)

        # Use connect() for source to ensure PRAGMAs are set (though backup() is low-level)
        source_conn = self.connect()
        # Destination is a raw new connection
        dest_conn = sqlite3.connect(str(target))
        try:
            source_conn.backup(dest_conn)
        finally:
            dest_conn.close()
            source_conn.close()

        # 4. Immediate verification
        if not self.verify_backup(target):
            if target.exists():
                target.unlink()
            raise PortfolioBookError(f"Backup verification failed for {target}")

        _log.info("Backup created and verified at %s", target)
        return target

    def verify_backup(self, backup_path: str | Path) -> bool:
        """Verify the integrity and compatibility of a backup file.

        Checks:
        1. File exists and is a valid SQLite database.
        2. PRAGMA integrity_check returns 'ok'.
        3. _schema_meta table exists and contains a valid version.
        4. Version is not higher than CURRENT_SCHEMA_VERSION.
        5. Core tables for the stated version are present.
        """
        path = Path(backup_path)
        if not path.exists():
            return False

        conn = None
        try:
            conn = sqlite3.connect(str(path))
            # 1. Integrity check
            cursor = conn.execute("PRAGMA integrity_check")
            rows = cursor.fetchall()
            if not rows or rows[0][0] != "ok":
                _log.error("Backup %s failed integrity check", path)
                return False

            # 2. Check metadata table
            cursor = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='_schema_meta'"
            )
            if not cursor.fetchone():
                _log.error("Backup %s missing _schema_meta table", path)
                return False

            # 3. Check version
            cursor = conn.execute(
                "SELECT value FROM _schema_meta WHERE key = 'version'"
            )
            row = cursor.fetchone()
            if not row:
                _log.error("Backup %s missing version in _schema_meta", path)
                return False

            version = int(row[0])
            if version > self.CURRENT_SCHEMA_VERSION:
                _log.warning(
                    "Backup %s version %d is newer than supported %d",
                    path, version, self.CURRENT_SCHEMA_VERSION
                )
                return False

            # 4. Check core tables for the version
            cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
            actual_tables = {r[0] for r in cursor.fetchall()}

            required = []
            if version >= 1: required.append("accounts")
            if version >= 2: required.append("products")
            if version >= 3: required.extend(["snapshot_batches", "position_snapshots"])
            if version >= 4: required.append("cashflow_events")
            if version >= 6: required.append("snapshot_batch_accounts")
            if version >= 8: required.extend(["import_drafts", "import_candidates"])
            if version >= 9: required.extend(["exposure_batches", "product_exposures"])

            for table in required:
                if table not in actual_tables:
                    _log.error("Backup %s missing core table: %s", path, table)
                    return False

            return True
        except (sqlite3.Error, ValueError, TypeError) as exc:
            _log.error("Verification failed for %s: %s", path, exc)
            return False
        finally:
            if conn:
                conn.close()

    def restore_from(self, backup_path: str | Path, overwrite: bool = False) -> None:
        """Atomically restore the database from a backup file.

        The process involves:
        1. Verifying the backup file.
        2. Restoring into a temporary file in the same directory.
        3. Running migrations on the temporary file if needed.
        4. Verifying the final temporary database.
        5. Atomically replacing the current database with the temporary one.

        Args:
            backup_path: Path to the backup file.
            overwrite: If True, allow replacing an existing database file.

        Raises:
            PortfolioBookError: if verification fails.
            FileExistsError: if target exists and overwrite is False.
            UnsupportedSchemaVersionError: if backup version is too new.
        """
        backup_path = Path(backup_path)

        # 1. Full verify before restore
        if not self.verify_backup(backup_path):
            raise PortfolioBookError(f"Invalid backup file: {backup_path}")

        # 2. Check target existence
        if self._path.exists() and not overwrite:
            raise FileExistsError(
                f"Database already exists at {self._path}. Use overwrite=True."
            )

        self._path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = self._path.with_suffix(".restore.tmp")

        try:
            # 3. Restore into temp file
            source_conn = sqlite3.connect(str(backup_path))
            temp_conn = sqlite3.connect(str(temp_path))
            try:
                source_conn.backup(temp_conn)
            finally:
                temp_conn.close()
                source_conn.close()

            # 4. Initialize (runs migrations + version check)
            temp_db = PortfolioBookDatabase(path=temp_path)
            temp_db.initialize()

            # 5. Final verify of migrated temp file
            if not self.verify_backup(temp_path):
                raise PortfolioBookError("Restored temporary database failed verification.")

            # 6. Atomic replace
            # Note: Path.replace() is atomic on POSIX.
            temp_path.replace(self._path)
            _log.info("Database restored atomically from %s", backup_path)
        finally:
            # 7. Cleanup
            if temp_path.exists():
                try:
                    temp_path.unlink()
                except OSError as exc:
                    _log.warning("Failed to clean up temp restore file %s: %s", temp_path, exc)

    @property
    def path(self) -> Path:
        """The resolved database file path (read-only)."""
        return self._path

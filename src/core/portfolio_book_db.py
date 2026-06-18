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
from contextlib import closing
from pathlib import Path
from typing import Optional, Any

from src.core.paths import PROJECT_ROOT

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
    - No business tables yet (accounts, products, etc. are added by
      follow-up tasks).
    - Schema version is stored in a ``_schema_meta`` metadata table.
    - Higher versions are rejected (no silent downgrade).
    - Connections always enable foreign keys and use ``sqlite3.Row``.
    """

    CURRENT_SCHEMA_VERSION: int = 2

    _migrations: dict[int, str] = {
        1: "_migrate_v1",
    }

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
                # New database: start at v1 and migrate up
                stored = 1
                conn.execute(
                    "INSERT INTO _schema_meta (key, value) VALUES ('version', '1')"
                )
                conn.commit()
            else:
                stored = int(row[0])

            if stored > self.CURRENT_SCHEMA_VERSION:
                raise UnsupportedSchemaVersionError(
                    f"Database schema version {stored} is higher than "
                    f"this code supports ({self.CURRENT_SCHEMA_VERSION}). "
                    f"Upgrade OptiFolio or use a compatible database."
                )

            # Apply migrations sequentially
            while stored < self.CURRENT_SCHEMA_VERSION:
                mig_name = self._migrations.get(stored)
                if mig_name:
                    getattr(self, mig_name)(conn)
                    _log.info("Applied migration %s to %s", mig_name, self._path.name)

                stored += 1
                conn.execute(
                    "INSERT OR REPLACE INTO _schema_meta (key, value) VALUES ('version', ?)",
                    (str(stored),),
                )
                conn.commit()

            _log.debug("PortfolioBookDatabase at v%d", stored)
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

    def _migrate_v1(self, conn: sqlite3.Connection) -> None:
        """Create the accounts table."""
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

    # ── Accounts CRUD ───────────────────────────────────────────────────

    def create_account(
        self,
        account_id: str,
        name: str,
        institution: str = "",
        account_type: str = "brokerage",
        base_currency: str = "CNY",
        ownership_scope: str = "personal",
        notes: str = "",
    ) -> None:
        """Create a new account.

        Args:
            account_id: Unique identifier.
            name: Display name.
            institution: Financial institution name.
            account_type: e.g., 'brokerage', 'savings', 'retirement'.
            base_currency: e.g., 'CNY', 'USD'.
            ownership_scope: 'personal' or 'joint'.
            notes: Optional notes.

        Raises:
            ValueError: if ownership_scope is invalid.
            sqlite3.IntegrityError: if account_id is not unique.
        """
        if ownership_scope not in ("personal", "joint"):
            raise ValueError(
                f"Invalid ownership_scope: {ownership_scope}. Must be 'personal' or 'joint'."
            )

        with closing(self.connect()) as conn:
            with conn:
                conn.execute(
                    "INSERT INTO accounts (account_id, name, institution, account_type, "
                    "  base_currency, ownership_scope, notes) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        account_id,
                        name,
                        institution,
                        account_type,
                        base_currency,
                        ownership_scope,
                        notes,
                    ),
                )

    def get_account(self, account_id: str) -> Optional[sqlite3.Row]:
        """Return the account record, or None if not found."""
        with closing(self.connect()) as conn:
            cursor = conn.execute(
                "SELECT * FROM accounts WHERE account_id = ?", (account_id,)
            )
            return cursor.fetchone()

    def update_account(self, account_id: str, **kwargs: Any) -> None:
        """Update account fields.

        Args:
            account_id: The account to update.
            **kwargs: Field names and new values. Supported: name, institution,
                account_type, base_currency, ownership_scope, status, notes.

        Raises:
            ValueError: if ownership_scope or status is invalid.
        """
        if "ownership_scope" in kwargs:
            scope = kwargs["ownership_scope"]
            if scope not in ("personal", "joint"):
                raise ValueError(
                    f"Invalid ownership_scope: {scope}. Must be 'personal' or 'joint'."
                )

        if "status" in kwargs:
            status = kwargs["status"]
            if status not in ("active", "inactive"):
                raise ValueError(
                    f"Invalid status: {status}. Must be 'active' or 'inactive'."
                )

        if not kwargs:
            return

        fields = []
        values = []
        for key, value in kwargs.items():
            fields.append(f"{key} = ?")
            values.append(value)

        # Always update updated_at
        fields.append("updated_at = (datetime('now'))")
        values.append(account_id)

        sql = f"UPDATE accounts SET {', '.join(fields)} WHERE account_id = ?"

        with closing(self.connect()) as conn:
            with conn:
                conn.execute(sql, tuple(values))

    def deactivate_account(self, account_id: str) -> None:
        """Set account status to 'inactive'."""
        self.update_account(account_id, status="inactive")

    def backup(self, target_path: str | Path) -> Path:
        """Create a consistent backup of the current database.

        Args:
            target_path: Destination for the backup file.

        Returns:
            The resolved backup Path.
        """
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
        """Check if a file is a valid portfolio book backup.

        Returns True if the file is a SQLite database with a valid
        _schema_meta version, False otherwise.
        """
        path = Path(backup_path)
        if not path.exists():
            return False

        try:
            # We use a temporary DB instance to check the version
            tmp_db = PortfolioBookDatabase(path=path)
            # schema_version() raises if _schema_meta is missing or corrupt
            tmp_db.schema_version()
            return True
        except (PortfolioBookError, sqlite3.Error, FileNotFoundError):
            return False

    def restore_from(self, backup_path: str | Path, overwrite: bool = False) -> None:
        """Restore the database from a backup file.

        Args:
            backup_path: Path to the backup file.
            overwrite: If True, replace an existing database file.

        Raises:
            FileExistsError: if the target database exists and overwrite=False.
            PortfolioBookError: if the backup is invalid or incompatible.
        """
        backup_path = Path(backup_path)
        if not self.verify_backup(backup_path):
            raise PortfolioBookError(f"Invalid backup file: {backup_path}")

        if self._path.exists() and not overwrite:
            raise FileExistsError(
                f"Database already exists at {self._path}. "
                f"Use overwrite=True to restore anyway."
            )

        # Check version compatibility before restoring
        backup_db = PortfolioBookDatabase(path=backup_path)
        backup_version = backup_db.schema_version()
        if backup_version > self.CURRENT_SCHEMA_VERSION:
            raise UnsupportedSchemaVersionError(
                f"Backup version {backup_version} is higher than "
                f"this code supports ({self.CURRENT_SCHEMA_VERSION})."
            )

        # Use sqlite3 backup for consistent restore
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

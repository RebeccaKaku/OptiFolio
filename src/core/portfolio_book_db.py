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
from pathlib import Path
from typing import Optional

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

    CURRENT_SCHEMA_VERSION: int = 1

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
                # First-time init: write current version
                conn.execute(
                    "INSERT INTO _schema_meta (key, value) VALUES ('version', ?)",
                    (str(self.CURRENT_SCHEMA_VERSION),),
                )
                conn.commit()
                _log.info(
                    "PortfolioBookDatabase initialized at %s (v%d)",
                    self._path, self.CURRENT_SCHEMA_VERSION,
                )
            else:
                stored = int(row[0])
                if stored > self.CURRENT_SCHEMA_VERSION:
                    raise UnsupportedSchemaVersionError(
                        f"Database schema version {stored} is higher than "
                        f"this code supports ({self.CURRENT_SCHEMA_VERSION}). "
                        f"Upgrade OptiFolio or use a compatible database."
                    )
                # stored <= CURRENT — already compatible, nothing to do
                _log.debug(
                    "PortfolioBookDatabase already at v%d (current: v%d)",
                    stored, self.CURRENT_SCHEMA_VERSION,
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

    # ── Future extension point ──────────────────────────────────────────

    # Migration dispatch placeholder.  When DS-002 (accounts) needs to
    # create business tables, add a private _migrate(version: int) method
    # and call it from initialize() after confirming the version.
    #
    # _migrations: dict[int, Callable[[sqlite3.Connection], None]] = {
    #     # 1: _migrate_v1_create_accounts,
    #     # 2: _migrate_v2_create_products,
    # }

    @property
    def path(self) -> Path:
        """The resolved database file path (read-only)."""
        return self._path

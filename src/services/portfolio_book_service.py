"""Portfolio book service — safe CRUD for accounts and products.

The service is injected with a ``PortfolioBookDatabase`` instance so tests
can point at temporary databases.  It translates database rows and dataclasses
into plain JSON-safe dictionaries and normalises all exceptions so callers
never see raw SQLite errors or internal stack traces.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from src.core.portfolio_book_db import PortfolioBookDatabase, PortfolioBookError
from src.domain.products import ProductDefinition
from src.services.response import success, failure

_log = logging.getLogger(__name__)

# ── PII detection ───────────────────────────────────────────────────────────

_PII_FIELD_NAMES: frozenset[str] = frozenset(
    {
        "password", "passwd", "pwd", "secret", "token",
        "api_key", "access_key", "private_key", "api_secret",
        "bank_card", "card_number", "credit_card", "debit_card",
        "card_no", "bank_account", "bank_account_number", "account_number",
        "account_no",
        "customer_id", "customer_no", "client_id", "client_no",
        "id_number", "id_card", "national_id", "ssn", "passport",
        "social_security", "tax_id", "driver_license",
        "密码", "银行卡号", "客户号", "证件号", "身份证",
    }
)


def _scan_pii(data: Dict[str, Any], prefix: str = "") -> Optional[str]:
    """Return the first nested PII-like field path, or ``None``."""
    for key, value in data.items():
        path = f"{prefix}.{key}" if prefix else str(key)
        if str(key).lower() in _PII_FIELD_NAMES:
            return path
        if isinstance(value, dict):
            found = _scan_pii(value, path)
            if found:
                return found
        elif isinstance(value, list):
            for index, item in enumerate(value):
                if isinstance(item, dict):
                    found = _scan_pii(item, f"{path}[{index}]")
                    if found:
                        return found
    return None


# ── Helpers ─────────────────────────────────────────────────────────────────

def _row_to_dict(row) -> Dict[str, Any]:
    """Convert an sqlite3.Row to a plain dict."""
    return dict(row)


def _product_to_dict(p: ProductDefinition) -> Dict[str, Any]:
    """Convert a ProductDefinition to a JSON-safe dict."""
    d = p.to_dict()
    # Ensure metadata is always a dict
    if d.get("metadata") is None:
        d["metadata"] = {}
    return d


# ── Service ─────────────────────────────────────────────────────────────────

class PortfolioBookService:
    """Safe CRUD service for the personal portfolio book.

    Every public method returns a ``{success, data, message, error, timestamp}``
    dict suitable for direct JSON serialisation.  Validation and PII scanning
    happen here; the underlying database is never exposed to callers.
    """

    def __init__(self, db: PortfolioBookDatabase) -> None:
        self._db = db

    # ── Accounts ────────────────────────────────────────────────────────

    def list_accounts(self, status: str = "active") -> Dict[str, Any]:
        """List accounts, optionally filtered by status."""
        try:
            rows = self._db.list_accounts(status)
            return success([_row_to_dict(r) for r in rows])
        except ValueError as exc:
            return failure(str(exc), error_code="VALIDATION_ERROR")
        except PortfolioBookError as exc:
            return failure(str(exc), error_code="DATABASE_ERROR")
        except Exception:
            _log.exception("Unexpected error listing accounts")
            return failure("Internal server error", error_code="INTERNAL_ERROR")

    def get_account(self, account_id: str) -> Dict[str, Any]:
        """Get a single account by ID."""
        try:
            row = self._db.get_account(account_id)
            if row is None:
                return failure(
                    f"Account {account_id!r} not found",
                    error_code="NOT_FOUND",
                )
            return success(_row_to_dict(row))
        except PortfolioBookError as exc:
            return failure(str(exc), error_code="DATABASE_ERROR")
        except Exception:
            _log.exception("Unexpected error getting account %r", account_id)
            return failure("Internal server error", error_code="INTERNAL_ERROR")

    def create_account(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new account.

        Required fields: ``account_id``, ``name``.
        Optional: ``institution``, ``account_type``, ``base_currency``,
        ``ownership_scope``, ``notes``.
        """
        try:
            pii_field = _scan_pii(data)
            if pii_field:
                return failure(
                    f"Field {pii_field!r} looks like sensitive personal information "
                    f"and is not accepted",
                    error_code="PII_REJECTED",
                )

            base_currency = data.get("base_currency", "CNY")
            if isinstance(base_currency, str):
                base_currency = base_currency.upper()
            self._db.create_account(
                account_id=data["account_id"],
                name=data["name"],
                institution=data.get("institution", ""),
                account_type=data.get("account_type", "brokerage"),
                base_currency=base_currency,
                ownership_scope=data.get("ownership_scope", "personal"),
                notes=data.get("notes", ""),
            )
            row = self._db.get_account(data["account_id"])
            return success(_row_to_dict(row), "Account created")
        except KeyError as exc:
            return failure(
                f"Missing required field: {exc.args[0]}",
                error_code="VALIDATION_ERROR",
            )
        except ValueError as exc:
            return failure(str(exc), error_code="VALIDATION_ERROR")
        except sqlite3_err as exc:
            return _handle_sqlite_error(exc)
        except PortfolioBookError as exc:
            return failure(str(exc), error_code="DATABASE_ERROR")
        except Exception:
            _log.exception("Unexpected error creating account")
            return failure("Internal server error", error_code="INTERNAL_ERROR")

    def update_account(self, account_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Update fields on an existing account.

        Only known update fields are forwarded to the database.
        """
        try:
            pii_field = _scan_pii(data)
            if pii_field:
                return failure(
                    f"Field {pii_field!r} looks like sensitive personal information "
                    f"and is not accepted",
                    error_code="PII_REJECTED",
                )

            changes = dict(data)
            if isinstance(changes.get("base_currency"), str):
                changes["base_currency"] = changes["base_currency"].upper()
            if self._db.get_account(account_id) is None:
                return failure(
                    f"Account {account_id!r} not found", error_code="NOT_FOUND"
                )
            self._db.update_account(account_id, **changes)
            row = self._db.get_account(account_id)
            return success(_row_to_dict(row), "Account updated")
        except ValueError as exc:
            return failure(str(exc), error_code="VALIDATION_ERROR")
        except PortfolioBookError as exc:
            return failure(str(exc), error_code="DATABASE_ERROR")
        except sqlite3_err as exc:
            return _handle_sqlite_error(exc)
        except Exception:
            _log.exception("Unexpected error updating account %r", account_id)
            return failure("Internal server error", error_code="INTERNAL_ERROR")

    def deactivate_account(self, account_id: str) -> Dict[str, Any]:
        """Mark an account as inactive."""
        try:
            if self._db.get_account(account_id) is None:
                return failure(
                    f"Account {account_id!r} not found", error_code="NOT_FOUND"
                )
            self._db.deactivate_account(account_id)
            row = self._db.get_account(account_id)
            return success(_row_to_dict(row), "Account deactivated")
        except PortfolioBookError as exc:
            return failure(str(exc), error_code="DATABASE_ERROR")
        except Exception:
            _log.exception("Unexpected error deactivating account %r", account_id)
            return failure("Internal server error", error_code="INTERNAL_ERROR")

    # ── Products ────────────────────────────────────────────────────────

    def list_products(self) -> Dict[str, Any]:
        """List all products."""
        try:
            products = self._db.list_products()
            return success([_product_to_dict(p) for p in products])
        except PortfolioBookError as exc:
            return failure(str(exc), error_code="DATABASE_ERROR")
        except Exception:
            _log.exception("Unexpected error listing products")
            return failure("Internal server error", error_code="INTERNAL_ERROR")

    def get_product(self, product_id: str) -> Dict[str, Any]:
        """Get a single product by ID."""
        try:
            p = self._db.get_product(product_id)
            if p is None:
                return failure(
                    f"Product {product_id!r} not found",
                    error_code="NOT_FOUND",
                )
            return success(_product_to_dict(p))
        except PortfolioBookError as exc:
            return failure(str(exc), error_code="DATABASE_ERROR")
        except Exception:
            _log.exception("Unexpected error getting product %r", product_id)
            return failure("Internal server error", error_code="INTERNAL_ERROR")

    def create_product(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new product from request data.

        Required fields are those of ``ProductDefinition``.
        Unknown extension fields go into ``metadata``.
        """
        try:
            pii_field = _scan_pii(data)
            if pii_field:
                return failure(
                    f"Field {pii_field!r} looks like sensitive personal information "
                    f"and is not accepted",
                    error_code="PII_REJECTED",
                )

            product = _dict_to_product(data)
            self._db.create_product(product)
            created = self._db.get_product(data["product_id"])
            return success(_product_to_dict(created), "Product created")
        except KeyError as exc:
            return failure(
                f"Missing required field: {exc.args[0]}",
                error_code="VALIDATION_ERROR",
            )
        except (ValueError, TypeError) as exc:
            return failure(str(exc), error_code="VALIDATION_ERROR")
        except sqlite3_err as exc:
            return _handle_sqlite_error(exc)
        except PortfolioBookError as exc:
            return failure(str(exc), error_code="DATABASE_ERROR")
        except Exception:
            _log.exception("Unexpected error creating product")
            return failure("Internal server error", error_code="INTERNAL_ERROR")

    def update_product(self, product_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Update an existing product.

        Merges update data with the existing product so partial updates work.
        """
        try:
            pii_field = _scan_pii(data)
            if pii_field:
                return failure(
                    f"Field {pii_field!r} looks like sensitive personal information "
                    f"and is not accepted",
                    error_code="PII_REJECTED",
                )

            existing = self._db.get_product(product_id)
            if existing is None:
                return failure(
                    f"Product {product_id!r} not found",
                    error_code="NOT_FOUND",
                )

            merged = _merge_product_update(existing, data)
            self._db.update_product(merged)
            updated = self._db.get_product(product_id)
            return success(_product_to_dict(updated), "Product updated")
        except (ValueError, TypeError) as exc:
            return failure(str(exc), error_code="VALIDATION_ERROR")
        except sqlite3_err as exc:
            return _handle_sqlite_error(exc)
        except PortfolioBookError as exc:
            return failure(str(exc), error_code="DATABASE_ERROR")
        except Exception:
            _log.exception("Unexpected error updating product %r", product_id)
            return failure("Internal server error", error_code="INTERNAL_ERROR")


# ── Internal helpers ────────────────────────────────────────────────────────

# Import here to avoid circular issues; used in except clauses.
import sqlite3 as _sqlite3
sqlite3_err = _sqlite3.Error  # alias for except clauses


def _handle_sqlite_error(exc: _sqlite3.Error) -> Dict[str, Any]:
    """Translate SQLite errors into safe failure responses."""
    msg = str(exc).lower()
    if "unique constraint" in msg:
        return failure("A record with this ID already exists", error_code="DUPLICATE")
    if "foreign key" in msg:
        return failure("Referenced record does not exist", error_code="FOREIGN_KEY_ERROR")
    _log.error("Unhandled SQLite error: %s", exc)
    return failure("Database error", error_code="DATABASE_ERROR")


def _dict_to_product(data: Dict[str, Any]) -> ProductDefinition:
    """Build a ProductDefinition from request dict, routing unknown fields to metadata."""
    known_fields = {
        "product_id", "name", "product_type", "issuer", "manager",
        "currency", "risk_level", "liquidity_type", "fee_policy_id",
        "benchmark_id", "primary_instrument_id", "data_source",
    }
    kwargs: Dict[str, Any] = {}
    extra: Dict[str, Any] = {}

    for key, value in data.items():
        if key == "metadata":
            if isinstance(value, dict):
                extra.update(value)
        elif key in known_fields:
            kwargs[key] = value
        else:
            extra[key] = value

    kwargs.setdefault("currency", "CNY")
    kwargs.setdefault("data_source", "manual")
    for field_name in ("product_id", "name", "product_type"):
        value = kwargs.get(field_name)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{field_name} must not be empty")
    currency = kwargs["currency"]
    if not isinstance(currency, str) or len(currency) != 3 or not currency.isalpha():
        raise ValueError("currency must be a 3-letter currency code")
    kwargs["currency"] = currency.upper()
    kwargs["metadata"] = extra
    return ProductDefinition(**kwargs)


def _merge_product_update(
    existing: ProductDefinition, update_data: Dict[str, Any]
) -> ProductDefinition:
    """Merge update data into an existing ProductDefinition."""
    d = _product_to_dict(existing)
    # If update provides metadata, merge it; otherwise keep existing
    changes = dict(update_data)
    if "metadata" in changes:
        update_meta = changes.pop("metadata")
        if isinstance(update_meta, dict):
            merged_meta = {**d.get("metadata", {}), **update_meta}
        else:
            merged_meta = d.get("metadata", {})
    else:
        merged_meta = d.get("metadata", {})

    for key, value in changes.items():
        if key in d:
            d[key] = value
        else:
            merged_meta[key] = value

    d["metadata"] = merged_meta

    # Rebuild via _dict_to_product to get proper ProductDefinition construction
    return _dict_to_product(d)

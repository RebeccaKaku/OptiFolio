"""Portfolio price ingestion — fetch and store via FinData pipeline.

Routes all fetch requests through FinData fetcher_dept and storage_dept.
No direct fetcher imports — uses the registry and QualityGate.
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd
import yaml
import sqlite3

from findata.adapters import get_fetcher
from findata.store import CanonicalStore
from findata.calendars import get_timezone

# PROJECT_ROOT resolved via environment or cwd walk (avoids src.core.paths import)
def _find_project_root() -> Path:
    """Walk up from cwd to find project root (dir containing pyproject.toml)."""
    from pathlib import Path as _Path
    cwd = _Path.cwd()
    for parent in [cwd, *cwd.parents]:
        if (parent / "pyproject.toml").exists():
            return parent
    return cwd


def load_portfolio(project_root: Path | None = None) -> tuple[Dict[str, float], Dict[str, float]]:
    """Load holdings and cash from the SQLite portfolio book only."""
    root = project_root or _find_project_root()
    sqlite_book = root / "local" / "portfolio_book.sqlite"
    if not sqlite_book.exists():
        return {}, {}
    return _load_sqlite_latest_batch(sqlite_book)


def _load_sqlite_latest_batch(path: Path) -> tuple[Dict[str, float], Dict[str, float]]:
    holdings: Dict[str, float] = {}
    cash: Dict[str, float] = {}
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        batch = conn.execute(
            """
            SELECT batch_id FROM snapshot_batches
            WHERE status = 'confirmed' AND as_of <= date('now')
            ORDER BY as_of DESC, created_at DESC
            LIMIT 1
            """
        ).fetchone()
        if not batch:
            return {}, {}

        rows = conn.execute(
            """
            SELECT ps.product_id, ps.quantity, ps.market_value, ps.currency, p.product_type
            FROM position_snapshots ps
            LEFT JOIN products p ON p.product_id = ps.product_id
            WHERE ps.batch_id = ?
            """,
            (batch["batch_id"],),
        ).fetchall()
        for row in rows:
            pid = str(row["product_id"])
            qty = row["quantity"]
            market_value = row["market_value"]
            product_type = (row["product_type"] or "").lower()
            if pid.endswith("_CASH") or product_type == "deposit":
                amount = qty if qty is not None else market_value
                if amount is not None:
                    currency = pid.replace("_CASH", "") if pid.endswith("_CASH") else (row["currency"] or "CNY")
                    cash[currency] = cash.get(currency, 0.0) + float(amount)
                continue
            if qty is not None and float(qty) > 0:
                holdings[pid] = holdings.get(pid, 0.0) + float(qty)
        return holdings, cash
    finally:
        conn.close()


def _sqlite_product_meta(symbol: str, project_root: Path | None = None) -> Dict[str, Any] | None:
    root = project_root or _find_project_root()
    path = root / "local" / "portfolio_book.sqlite"
    if not path.exists():
        return None
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(
            "SELECT product_type, currency, name FROM products WHERE product_id = ?",
            (symbol,),
        ).fetchone()
        if not row:
            return None
        product_type = (row["product_type"] or "").lower()
        if symbol.startswith("fund.cn.") or "fund" in product_type:
            asset_type = "cn_fund"
        elif symbol.startswith("wmp.cn.") or "wmp" in product_type or "bank" in product_type:
            asset_type = "bank_wmp"
        elif symbol.startswith("equity.cn."):
            asset_type = "cn_stock"
        elif symbol.startswith("equity.us."):
            asset_type = "us_equity"
        else:
            asset_type = product_type
        return {
            "currency": row["currency"] or "CNY",
            "type": asset_type,
            "name": row["name"] or symbol,
        }
    finally:
        conn.close()


def resolve_meta(symbol: str) -> Dict[str, Any]:
    """Resolve asset type + currency from registry → SQLite book → heuristic."""
    for cfg in ["config/asset_registry.yaml", "config/candidates.yaml"]:
        path = _find_project_root() / cfg
        if path.exists():
            with open(path, encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            for entry in data.get("assets", []):
                if entry.get("symbol") == symbol:
                    return {
                        "currency": entry.get("currency", "USD"),
                        "type": entry.get("asset_type", ""),
                        "name": entry.get("name", symbol),
                    }

    sqlite_meta = _sqlite_product_meta(symbol)
    if sqlite_meta:
        return sqlite_meta

    # Heuristic
    lowered = symbol.lower()
    if lowered.startswith("equity.cn.") or symbol.startswith(("sh", "sz")):
        return {"currency": "CNY", "type": "cn_stock", "name": symbol}
    if lowered.startswith("equity.us."):
        return {"currency": "USD", "type": "us_equity", "name": symbol}
    if lowered.startswith("fund.cn."):
        return {"currency": "CNY", "type": "cn_fund", "name": symbol}
    if lowered.startswith("wmp.cn."):
        return {"currency": "CNY", "type": "bank_wmp", "name": symbol}
    if symbol.isdigit() and len(symbol) == 6:
        return {"currency": "CNY", "type": "cn_fund" if symbol.startswith(("00", "16", "15", "50")) else "cn_stock", "name": symbol}
    if symbol.isalpha() and symbol.isupper() and len(symbol) <= 5:
        return {"currency": "USD", "type": "us_equity", "name": symbol}
    return {"currency": "USD", "type": "unknown", "name": symbol}


def ingest_portfolio(
    symbols: Optional[List[str]] = None,
    years: int = 2,
    dry_run: bool = False,
    store: Optional[CanonicalStore] = None,
) -> Dict[str, Any]:
    """Ingest portfolio prices via FinData pipeline.

    Returns: {"ingested": [...], "no_data": [...], "failed": [...]}
    """
    holdings, _ = load_portfolio()
    if symbols:
        holdings = {s: holdings.get(s, 0) for s in symbols}
    if not holdings:
        return {"ingested": [], "no_data": [], "failed": []}

    if store is None:
        store = CanonicalStore()

    end_date = date.today().isoformat()
    start_date = (date.today() - timedelta(days=years * 365)).isoformat()

    if dry_run:
        plan = []
        for sym in holdings:
            meta = resolve_meta(sym)
            plan.append(f"{sym}: type={meta['type']}, currency={meta['currency']}")
        return {"plan": plan}

    result = {"ingested": [], "no_data": [], "failed": []}

    for symbol in holdings:
        meta = resolve_meta(symbol)
        atype = meta["type"]
        fetcher = get_fetcher(atype)

        if fetcher is None:
            result["failed"].append(f"{symbol}: no fetcher for type={atype}")
            continue

        try:
            fetch_result = fetcher.fetch(symbol, start_date, end_date)
        except Exception as exc:
            result["failed"].append(f"{symbol}: fetch error {exc}")
            continue

        if not fetch_result.success or fetch_result.data is None or fetch_result.data.empty:
            result["no_data"].append(symbol)
            continue

        tz = get_timezone(atype)
        report = store.accept(
            fetch_result.data, asset_id=symbol,
            source=fetch_result.provider, currency=meta["currency"],
            timezone=tz, asset_type=atype,
        )
        if report.passed:
            result["ingested"].append(symbol)
        else:
            result["failed"].append(f"{symbol}: quality rejected — {report.reject_reasons}")

    return result

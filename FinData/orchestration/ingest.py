"""Portfolio price ingestion — fetch and store via FinData pipeline.

Routes all fetch requests through FinData fetcher_dept and storage_dept.
No direct fetcher imports — uses the registry and QualityGate.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Dict, List, Optional

import pandas as pd
import yaml

from FinData.adapters import get_fetcher
from FinData.store.repository import CanonicalStore
from src.core.calendars import get_calendar

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
    root = project_root or _find_project_root()
    for loc in [root / "local" / "portfolio.yaml", root / "config" / "portfolio.yaml"]:
        if loc.exists():
            with open(loc, encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            h = {str(k): float(v) for k, v in data.get("positions", {}).items()}
            c = {str(k): float(v) for k, v in data.get("cash", {}).items()}
            return h, c
    return {}, {}


def resolve_meta(symbol: str) -> Dict[str, Any]:
    """Resolve asset type + currency from registry → candidates → heuristic."""
    for cfg in ["config/asset_registry.yaml", "config/candidates.yaml"]:
        path = PROJECT_ROOT / cfg
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
    # Heuristic
    if symbol.startswith(("sh", "sz")):
        return {"currency": "CNY", "type": "cn_stock", "name": symbol}
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

        cal = get_calendar(atype)
        report = store.accept(
            fetch_result.data, asset_id=symbol,
            source=fetch_result.provider, currency=meta["currency"],
            timezone=cal.timezone,
        )
        if report.passed:
            result["ingested"].append(symbol)
        else:
            result["failed"].append(f"{symbol}: quality rejected — {report.reject_reasons}")

    return result

#!/usr/bin/env python
"""Export OptiFolio portfolio holdings to Ghostfolio.

Converts current holdings into Ghostfolio BUY activities and POSTs them
to the Ghostfolio import API. Ghostfolio uses BUY activities to establish
current holdings — it tracks live prices internally.

Usage:
    python tools/export_to_ghostfolio.py --host http://localhost:3333 --token YOUR_JWT
    python tools/export_to_ghostfolio.py  # uses GHOSTFOLIO_HOST / GHOSTFOLIO_TOKEN env vars

Environment variables:
    GHOSTFOLIO_HOST   Ghostfolio instance URL (default: http://localhost:3333)
    GHOSTFOLIO_TOKEN  JWT bearer token (obtain from Ghostfolio admin panel)
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from findata.store import MarketDataRepository
from src.core.paths import PROJECT_ROOT
from src.core.valuation import _resolve_currency


# ── Symbol normalization ─────────────────────────────────────────────────


def normalize_symbol(asset_id: str) -> str:
    """Convert OptiFolio asset IDs to Ghostfolio-compatible tickers.

    Ghostfolio expects raw ticker symbols without exchange prefixes.
    - ``sh600519`` → ``600519`` (CN stocks strip sh/sz prefix)
    - ``AAPL`` → ``AAPL`` (US stocks pass through)
    - ``510300`` → ``510300`` (numeric ETF codes pass through)
    """
    asset_id = str(asset_id)
    if asset_id.lower().startswith("sh") and len(asset_id) == 8:
        return asset_id[2:]
    if asset_id.lower().startswith("sz") and len(asset_id) == 8:
        return asset_id[2:]
    return asset_id


# ── Ghostfolio API client ───────────────────────────────────────────────


class GhostfolioClient:
    """Thin HTTP wrapper around Ghostfolio's REST API."""

    def __init__(self, host: str, token: str, timeout: int = 30) -> None:
        self.host = host.rstrip("/")
        self.token = token
        self.timeout = timeout
        self._session = requests.Session()
        self._session.headers.update({
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        })

    def import_activities(self, activities: List[Dict[str, Any]]) -> Dict[str, Any]:
        """POST a list of activities to Ghostfolio's /api/import."""
        url = f"{self.host}/api/import"
        resp = self._session.post(
            url,
            json={"activities": activities},
            timeout=self.timeout,
        )
        resp.raise_for_status()
        return resp.json()

    def get_accounts(self) -> List[Dict[str, Any]]:
        """List all accounts in the Ghostfolio instance."""
        url = f"{self.host}/api/account"
        resp = self._session.get(url, timeout=self.timeout)
        resp.raise_for_status()
        return resp.json().get("accounts", [])

    def create_account(self, name: str, currency: str) -> Dict[str, Any]:
        """Create a new account in Ghostfolio."""
        url = f"{self.host}/api/account"
        payload = {
            "name": name,
            "currency": currency,
            "platformId": None,
            "isExcluded": False,
        }
        resp = self._session.post(url, json=payload, timeout=self.timeout)
        resp.raise_for_status()
        return resp.json()

    def get_or_create_account(self, name: str, currency: str) -> str:
        """Find an existing account by name or create one. Returns account ID."""
        accounts = self.get_accounts()
        for acct in accounts:
            if acct.get("name") == name:
                return acct["id"]

        result = self.create_account(name, currency)
        return result["id"]


# ── Exporter ─────────────────────────────────────────────────────────────


class GhostfolioExporter:
    """Convert OptiFolio holdings to Ghostfolio activities and push them.

    Usage::

        exporter = GhostfolioExporter("http://localhost:3333", "eyJ...")
        count = exporter.export_holdings(holdings, cash, prices, date.today().isoformat())
    """

    _ALLOWED_TYPES = {"BUY", "SELL", "DIVIDEND", "INTEREST", "FEE", "LIABILITY", "VALUABLE"}

    def __init__(self, host: str, token: str, timeout: int = 30) -> None:
        self.client = GhostfolioClient(host, token, timeout=timeout)

    # ── Public API ──────────────────────────────────────────────────────

    def get_or_create_account(self, name: str, currency: str) -> str:
        """Resolve or create a Ghostfolio account. Returns account ID."""
        return self.client.get_or_create_account(name, currency)

    def export_holdings(
        self,
        holdings: Dict[str, float],
        cash: Dict[str, float],
        prices: Dict[str, Optional[float]],
        date_str: str,
        account_id: Optional[str] = None,
        account_name: str = "OptiFolio",
        account_currency: str = "USD",
    ) -> int:
        """Convert holdings to Ghostfolio BUY activities and POST them.

        Args:
            holdings: {asset_id: quantity} from portfolio.yaml positions.
            cash: {currency: amount} from portfolio.yaml cash (not exported).
            prices: {asset_id: unit_price} — current price per share.
            date_str: ISO date string (e.g. ``"2026-06-03"``) for the activity date.
            account_id: Ghostfolio account UUID. If None, auto-resolved.
            account_name: Name for the account (used when auto-creating).
            account_currency: Currency for the account (used when auto-creating).

        Returns:
            Number of activities successfully imported.
        """
        if account_id is None:
            account_id = self.get_or_create_account(account_name, account_currency)

        activities = self._build_activities(holdings, prices, date_str, account_id)

        if not activities:
            print("No holdings to export.")
            return 0

        result = self.client.import_activities(activities)
        imported = len(result.get("activities", []))
        print(f"Exported {imported} activities to Ghostfolio.")
        return imported

    def export_valuation_history(self, history_df: "pd.DataFrame") -> int:
        """Not applicable for Ghostfolio.

        Ghostfolio tracks prices internally — it does not ingest historical
        valuations. Use ``export_holdings`` to push a portfolio snapshot as
        BUY activities, and Ghostfolio will compute valuations from live
        market prices.

        Returns:
            Always 0 (no-op).
        """
        print("export_valuation_history is not applicable for Ghostfolio — "
              "it computes valuations from live prices internally.")
        return 0

    # ── Activity building ───────────────────────────────────────────────

    def _build_activities(
        self,
        holdings: Dict[str, float],
        prices: Dict[str, Optional[float]],
        date_str: str,
        account_id: str,
    ) -> List[Dict[str, Any]]:
        """Build Ghostfolio BUY activity dicts from OptiFolio holdings.

        Filters out positions with zero quantity or missing price data.
        """
        dt = self._format_datetime(date_str)
        activities: List[Dict[str, Any]] = []

        for asset_id, quantity in sorted(holdings.items()):
            qty = float(quantity)
            if qty <= 0:
                continue

            symbol = normalize_symbol(asset_id)
            currency = _resolve_currency(asset_id)
            unit_price = prices.get(asset_id)

            if unit_price is None:
                print(f"  Skipping {asset_id}: no price data available")
                continue

            activity = {
                "accountId": account_id,
                "comment": f"Imported from OptiFolio — {asset_id}",
                "currency": currency,
                "dataSource": "MANUAL",
                "date": dt,
                "fee": 0.0,
                "quantity": qty,
                "symbol": symbol,
                "type": "BUY",
                "unitPrice": round(float(unit_price), 4),
            }
            activities.append(activity)

        return activities

    @staticmethod
    def _format_datetime(date_str: str) -> str:
        """Format a date string as Ghostfolio's expected ISO datetime."""
        try:
            d = date.fromisoformat(date_str)
        except ValueError:
            d = date.today()
        return datetime(d.year, d.month, d.day, tzinfo=timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%S.000Z"
        )


# ── Portfolio loading helpers ────────────────────────────────────────────


def load_portfolio() -> tuple[Dict[str, float], Dict[str, float]]:
    """Load portfolio holdings and cash from YAML.

    Resolution order: OPTIFOLIO_PORTFOLIO_PATH env var → local/portfolio.yaml
    → config/portfolio.yaml.
    """
    env_path = os.environ.get("OPTIFOLIO_PORTFOLIO_PATH")
    if env_path:
        path = Path(env_path)
        if path.exists():
            return _read_portfolio_yaml(path)

    local_path = PROJECT_ROOT / "local" / "portfolio.yaml"
    if local_path.exists():
        return _read_portfolio_yaml(local_path)

    legacy_path = PROJECT_ROOT / "config" / "portfolio.yaml"
    if legacy_path.exists():
        return _read_portfolio_yaml(legacy_path)

    return {}, {}


def _read_portfolio_yaml(path: Path) -> tuple[Dict[str, float], Dict[str, float]]:
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    holdings = {str(k): float(v) for k, v in data.get("positions", {}).items()}
    cash = {str(k): float(v) for k, v in data.get("cash", {}).items()}
    return holdings, cash


def load_latest_prices(
    holdings: Dict[str, float],
    repo: Optional[MarketDataRepository] = None,
) -> Dict[str, Optional[float]]:
    """Get the latest available price for each holding from MarketDataRepository.

    Returns a dict mapping each asset_id to its most recent close price,
    or None if no price data is available.
    """
    if repo is None:
        repo = MarketDataRepository()

    prices: Dict[str, Optional[float]] = {}
    today = date.today()
    lookback_start = (today - __import__("datetime").timedelta(days=10)).isoformat()
    end_str = today.isoformat()

    for asset_id in sorted(holdings.keys()):
        try:
            df = repo.get_prices(
                [asset_id],
                start=lookback_start,
                end=end_str,
            )
            if not df.empty and asset_id in df.columns:
                col = df[asset_id].dropna()
                if not col.empty:
                    prices[asset_id] = float(col.iloc[-1])
                    continue
        except Exception:
            pass
        prices[asset_id] = None

    return prices


# ── Configuration helpers ────────────────────────────────────────────────


def _resolve_config(args_host: Optional[str], args_token: Optional[str]) -> tuple[str, str]:
    """Resolve Ghostfolio host and token from CLI args or env vars."""
    host = args_host or os.environ.get("GHOSTFOLIO_HOST", "http://localhost:3333")
    token = args_token or os.environ.get("GHOSTFOLIO_TOKEN", "")
    if not token:
        print("Error: Ghostfolio JWT token is required.")
        print("  Set GHOSTFOLIO_TOKEN env var or pass --token")
        sys.exit(1)
    return host, token


# ── CLI ──────────────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Export OptiFolio portfolio holdings to Ghostfolio",
    )
    parser.add_argument(
        "--host",
        help="Ghostfolio instance URL (default: http://localhost:3333 or GHOSTFOLIO_HOST env var)",
    )
    parser.add_argument(
        "--token",
        help="Ghostfolio JWT token (default: GHOSTFOLIO_TOKEN env var)",
    )
    parser.add_argument(
        "--account-name",
        default="OptiFolio",
        help="Ghostfolio account name (default: OptiFolio)",
    )
    parser.add_argument(
        "--account-currency",
        default="USD",
        help="Ghostfolio account currency (default: USD)",
    )
    parser.add_argument(
        "--date",
        default=date.today().isoformat(),
        help=f"Date for activities in YYYY-MM-DD (default: today, {date.today().isoformat()})",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show activities without posting to Ghostfolio",
    )
    args = parser.parse_args()

    host, token = _resolve_config(args.host, args.token)

    # Load portfolio
    holdings, cash = load_portfolio()
    if not holdings:
        print("No holdings found in portfolio.yaml.")
        return

    # Load prices
    repo = MarketDataRepository()
    prices = load_latest_prices(holdings, repo)

    # Build exporter
    exporter = GhostfolioExporter(host, token)

    # Resolve account ID
    account_id = exporter.get_or_create_account(args.account_name, args.account_currency)
    print(f"Account ID: {account_id}")

    # Build activities
    activities = exporter._build_activities(holdings, prices, args.date, account_id)

    print(f"\nActivities to export ({len(activities)}):")
    for act in activities:
        print(f"  {act['type']:>8s} {act['quantity']:>10.2f} x {act['symbol']:<10s} "
              f"@ {act['unitPrice']:>12.4f} {act['currency']}")

    if args.dry_run:
        print("\n[Dry run — no data posted]")
        return

    # Post to Ghostfolio
    result = exporter.client.import_activities(activities)
    imported = len(result.get("activities", []))
    print(f"\nSuccessfully imported {imported} activities into Ghostfolio.")


if __name__ == "__main__":
    main()

"""Ghostfolio-compatible API adapter for OptiFolio."""

import asyncio
import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field
from src.services import get_application_services

router = APIRouter(prefix="/api/v1")
logger = logging.getLogger("ghostfolio_compat")


# ── Response schemas (Pydantic v2) ──────────────────────────────────────────


class GhostfolioHolding(BaseModel):
    symbol: str
    name: str
    quantity: float
    marketPrice: float
    currency: str
    allocationInPercentage: float
    performance: float
    assetClass: str
    assetSubClass: str


class GhostfolioSummary(BaseModel):
    currentNetWorth: float
    totalInvestment: float
    grossPerformance: float
    grossPerformancePercentage: float


class GhostfolioDetailsResponse(BaseModel):
    accounts: List[dict] = []
    holdings: Dict[str, GhostfolioHolding] = {}
    summary: GhostfolioSummary = Field(default_factory=lambda: GhostfolioSummary(
        currentNetWorth=0.0, totalInvestment=0.0, grossPerformance=0.0, grossPerformancePercentage=0.0
    ))
    platforms: List[dict] = []
    hasError: bool = False


class GhostfolioPerformanceChartItem(BaseModel):
    date: str
    netWorth: float
    netPerformanceInPercentage: float
    totalInvestment: float
    value: float


class GhostfolioPerformanceResponse(BaseModel):
    chart: List[GhostfolioPerformanceChartItem] = []
    performance: GhostfolioSummary = Field(default_factory=lambda: GhostfolioSummary(
        currentNetWorth=0.0, totalInvestment=0.0, grossPerformance=0.0, grossPerformancePercentage=0.0
    ))


class GhostfolioInvestment(BaseModel):
    date: str
    investment: float


class GhostfolioStreaks(BaseModel):
    currentStreak: int
    longestStreak: int


class GhostfolioInvestmentsResponse(BaseModel):
    investments: List[GhostfolioInvestment] = []
    streaks: GhostfolioStreaks = Field(default_factory=lambda: GhostfolioStreaks(currentStreak=1, longestStreak=1))


class GhostfolioReportResponse(BaseModel):
    xRay: dict = {"categories": [], "statistics": {"totalCount": 0}}

# Re-use the canonical classification from ExposureAnalyzer for consistency.
from src.analytics.exposure import ExposureAnalyzer

_EXPOSURE_ANALYZER = ExposureAnalyzer()


def _to_ghostfolio_class(optifolio_class: str) -> str:
    """Map OptiFolio asset-class buckets to Ghostfolio asset classes."""
    mapping = {
        "equity": "EQUITY",
        "fixed_income": "FIXED_INCOME",
        "cash": "CASH",
        "alternative": "OTHER",
    }
    return mapping.get(optifolio_class, "OTHER")


def _to_ghostfolio_sub_class(optifolio_class: str, asset_type: str) -> str:
    """Map OptiFolio asset-class buckets to Ghostfolio sub-classes."""
    at = str(asset_type).lower()
    if optifolio_class == "equity":
        if "etf" in at or "lof" in at or "index" in at:
            return "ETF"
        return "STOCK"
    if optifolio_class == "fixed_income":
        return "BOND"
    if optifolio_class == "cash":
        return "CASH"
    return "OTHER"


def _resolve_asset_info(symbol: str) -> Dict[str, Any]:
    """Fetch asset info and enrich with canonical classification."""
    services = get_application_services()
    asset_res = services.assets.get_asset_info(symbol)
    asset_data = (asset_res.get("data") or {}) if isinstance(asset_res, dict) else {}

    asset_type = asset_data.get("asset_type", "")
    optifolio_class = _EXPOSURE_ANALYZER.classify(
        asset_type,
        metadata=asset_data,
    )

    return {
        "name": asset_data.get("name", symbol),
        "asset_type": asset_type,
        "currency": asset_data.get("currency", "CNY"),
        "assetClass": _to_ghostfolio_class(optifolio_class),
        "assetSubClass": _to_ghostfolio_sub_class(optifolio_class, asset_type),
    }


@router.get("/portfolio/details", response_model=GhostfolioDetailsResponse)
async def ghostfolio_portfolio_details():
    """Main dashboard endpoint for Ghostfolio."""
    try:
        services = get_application_services()
        value_res = await asyncio.to_thread(
            services.portfolio_v2.get_value, base_currency="CNY"
        )
    except Exception as exc:
        logger.warning("Ghostfolio details failed: %s", exc)
        return {
            "hasError": True,
            "accounts": [],
            "holdings": {},
            "summary": {
                "currentNetWorth": 0.0,
                "totalInvestment": 0.0,
                "grossPerformance": 0.0,
                "grossPerformancePercentage": 0.0,
            },
            "platforms": [],
        }

    if not value_res.get("success"):
        logger.info("Ghostfolio details: portfolio.get_value returned error")
        return {
            "hasError": True,
            "accounts": [],
            "holdings": {},
            "summary": {
                "currentNetWorth": 0.0,
                "totalInvestment": 0.0,
                "grossPerformance": 0.0,
                "grossPerformancePercentage": 0.0,
            },
            "platforms": [],
        }

    data = value_res.get("data") or {}
    total_value = data.get("total_value", 0.0)
    total_investment = total_value  # historical cost not yet tracked

    ghost_holdings = {}
    positions = data.get("positions", {})

    for symbol, pos in positions.items():
        try:
            info = _resolve_asset_info(symbol)
        except Exception as exc:
            logger.warning("Ghostfolio details: asset info for %s failed: %s", symbol, exc)
            info = {"name": symbol, "assetClass": "OTHER", "assetSubClass": "OTHER", "currency": "CNY"}

        ghost_holdings[symbol] = {
            "symbol": symbol,
            "name": info["name"],
            "quantity": pos.get("shares", 0),
            "marketPrice": pos.get("price", 0),
            "currency": pos.get("currency", info["currency"]),
            "allocationInPercentage": (
                (pos.get("value", 0) / total_value) if total_value > 0 else 0
            ),
            "performance": 0.0,
            "assetClass": info["assetClass"],
            "assetSubClass": info["assetSubClass"],
        }

    return {
        "accounts": [],
        "holdings": ghost_holdings,
        "summary": {
            "currentNetWorth": total_value,
            "totalInvestment": total_investment,
            "grossPerformance": 0.0,
            "grossPerformancePercentage": 0.0,
        },
        "platforms": [],
        "hasError": False,
    }


@router.get("/portfolio/performance", response_model=GhostfolioPerformanceResponse)
async def ghostfolio_portfolio_performance():
    """Performance chart data for Ghostfolio."""
    try:
        services = get_application_services()
        value_res = await asyncio.to_thread(
            services.portfolio_v2.get_value, base_currency="CNY"
        )
        chart_res = await asyncio.to_thread(
            services.portfolio_v2.get_value_history,
            start=(__import__("datetime").date.today() - __import__("datetime").timedelta(days=365)),
            end=__import__("datetime").date.today(),
            base_currency="CNY"
        )
    except Exception as exc:
        logger.warning("Ghostfolio performance failed: %s", exc)
        return {
            "chart": [],
            "performance": {
                "currentNetWorth": 0.0,
                "totalInvestment": 0.0,
                "grossPerformance": 0.0,
                "grossPerformancePercentage": 0.0,
            },
        }

    if not value_res.get("success") or not chart_res.get("success"):
        logger.info("Ghostfolio performance: upstream error")
        return {
            "chart": [],
            "performance": {
                "currentNetWorth": 0.0,
                "totalInvestment": 0.0,
                "grossPerformance": 0.0,
                "grossPerformancePercentage": 0.0,
            },
        }

    value_data = value_res.get("data") or {}
    history_records = chart_res.get("data", {}).get("records", [])

    total_value = value_data.get("total_value", 0.0)

    ghost_chart = []
    # Simplified performance calculation from history for Ghostfolio
    if history_records:
        start_val = history_records[0].get("total_value", 0.0)
        for record in history_records:
            curr_val = record.get("total_value", 0.0)
            ret = (curr_val / start_val - 1) if start_val > 0 else 0.0
            ghost_chart.append(
                {
                    "date": record.get("as_of") or record.get("date"),
                    "netWorth": curr_val,
                    "netPerformanceInPercentage": ret,
                    "totalInvestment": start_val,
                    "value": curr_val,
                }
            )

    return {
        "chart": ghost_chart,
        "performance": {
            "currentNetWorth": total_value,
            "totalInvestment": total_value,
            "grossPerformance": 0.0,
            "grossPerformancePercentage": 0.0,
            "currentValueInBaseCurrency": total_value,
        },
    }


@router.get("/portfolio/holdings", response_model=List[GhostfolioHolding])
async def ghostfolio_portfolio_holdings(
    symbol: Optional[str] = Query(None),
    query: Optional[str] = Query(None),
):
    """Holdings list for Ghostfolio.

    *query* matches against both symbol and asset name (case-insensitive).
    """
    try:
        services = get_application_services()
        value_res = await asyncio.to_thread(
            services.portfolio_v2.get_value, base_currency="CNY"
        )
    except Exception as exc:
        logger.warning("Ghostfolio holdings failed: %s", exc)
        return []

    if not value_res.get("success"):
        return []

    data = value_res.get("data") or {}
    positions = data.get("positions", {})
    total_value = data.get("total_value", 0.0)

    ghost_holdings = []
    for s, pos in positions.items():
        if symbol and s != symbol:
            continue

        try:
            info = _resolve_asset_info(s)
        except Exception as exc:
            logger.warning("Ghostfolio holdings: asset info for %s failed: %s", s, exc)
            info = {"name": s, "assetClass": "OTHER", "assetSubClass": "OTHER", "currency": "CNY"}

        # Support query on both symbol and name
        if query:
            q = query.lower()
            if q not in s.lower() and q not in info["name"].lower():
                continue

        ghost_holdings.append(
            {
                "symbol": s,
                "name": info["name"],
                "quantity": pos.get("shares", 0),
                "marketPrice": pos.get("price", 0),
                "currency": pos.get("currency", info["currency"]),
                "allocationInPercentage": (
                    (pos.get("value", 0) / total_value) if total_value > 0 else 0
                ),
                "performance": 0.0,
                "assetClass": info["assetClass"],
                "assetSubClass": info["assetSubClass"],
            }
        )

    return ghost_holdings


@router.get("/portfolio/dividends", response_model=List[dict])
async def ghostfolio_portfolio_dividends():
    """Dividends list for Ghostfolio."""
    try:
        services = get_application_services()
        res = services.portfolio_v2.get_corporate_actions()
        if not res.get("success"):
            return []

        actions = res.get("data", {}).get("actions", [])
        dividends = []
        for action in actions:
            if action.get("action_type") == "dividend":
                dividends.append(
                    {
                        "symbol": action.get("asset_id"),
                        "date": action.get("ex_date"),
                        "amount": action.get("dividend_per_share"),
                        "currency": action.get("dividend_currency"),
                    }
                )
        return dividends
    except Exception as exc:
        logger.warning("Ghostfolio dividends failed: %s", exc)
        return []


@router.get("/portfolio/investments", response_model=GhostfolioInvestmentsResponse)
async def ghostfolio_portfolio_investments():
    """Investment timeline for Ghostfolio."""
    try:
        from src.core.portfolio_book_db import PortfolioBookDatabase
        import pandas as pd
        from datetime import datetime

        db = PortfolioBookDatabase()
        query = """
            SELECT b.as_of, SUM(COALESCE(p.cost_basis, 0)) as cost_basis
            FROM position_snapshots p
            JOIN snapshot_batches b ON p.batch_id = b.batch_id
            WHERE b.status = 'confirmed'
            GROUP BY b.as_of
            ORDER BY b.as_of ASC
        """
        import sqlite3
        with sqlite3.connect(db.path) as conn:
            df = pd.read_sql_query(query, conn)

        if df.empty:
            return {
                "investments": [],
                "streaks": {"currentStreak": 0, "longestStreak": 0},
            }

        # Ensure as_of is datetime
        df["as_of"] = pd.to_datetime(df["as_of"])

        investments = []
        for _, row in df.iterrows():
            # as_of might be date string or datetime string
            dt = pd.to_datetime(row["as_of"])
            investments.append(
                {"date": dt.date().isoformat(), "investment": float(row["cost_basis"])}
            )

        # Streaks: consecutive months with data
        months = sorted(df["as_of"].dt.to_period("M").unique())
        current_streak = 0
        longest_streak = 0

        if months:
            streaks = []
            curr = 1
            for i in range(1, len(months)):
                if months[i] == months[i - 1] + 1:
                    curr += 1
                else:
                    streaks.append(curr)
                    curr = 1
            streaks.append(curr)

            longest_streak = max(streaks) if streaks else 0

            # Current streak: only if the latest month is recent (this month or last)
            today_period = pd.Period(datetime.now(), freq="M")
            if months[-1] >= today_period - 1:
                current_streak = streaks[-1]
            else:
                current_streak = 0

        return {
            "investments": investments,
            "streaks": {"currentStreak": current_streak, "longestStreak": longest_streak},
        }
    except Exception as exc:
        logger.warning("Ghostfolio investments failed: %s", exc)
        return {
            "investments": [],
            "streaks": {"currentStreak": 0, "longestStreak": 0},
        }


@router.get("/portfolio/report", response_model=GhostfolioReportResponse)
async def ghostfolio_portfolio_report():
    """Report stub for Ghostfolio."""
    try:
        services = get_application_services()
        res = services.portfolio_v2.get_exposure_report()
        if not res.get("success"):
            return {"xRay": {"categories": [], "statistics": {"totalCount": 0}}}

        data = res.get("data", {})
        by_asset_class = data.get("by_asset_class", [])

        categories = []
        all_asset_ids = set()
        for item in by_asset_class:
            asset_ids = item.get("asset_ids", [])
            all_asset_ids.update(asset_ids)
            categories.append(
                {
                    "name": item.get("bucket"),
                    "value": item.get("value"),
                    "percentage": item.get("pct"),
                    "assetIds": asset_ids,
                }
            )

        return {
            "xRay": {
                "categories": categories,
                "statistics": {"totalCount": len(all_asset_ids)},
            }
        }
    except Exception as exc:
        logger.warning("Ghostfolio report failed: %s", exc)
        return {"xRay": {"categories": [], "statistics": {"totalCount": 0}}}

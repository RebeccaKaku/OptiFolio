"""Ghostfolio-compatible API adapter for OptiFolio."""

from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Query
from src.services import get_application_services

router = APIRouter(prefix="/api/v1")

def map_asset_class(asset_type: str) -> str:
    """Map OptiFolio asset types to Ghostfolio asset classes."""
    mapping = {
        "us_equity": "EQUITY",
        "cn_stock": "EQUITY",
        "cn_fund": "FUND",
        "bank_wmp": "OTHER",
        "cash": "CASH"
    }
    return mapping.get(asset_type, "OTHER")

def map_asset_sub_class(asset_type: str) -> str:
    """Map OptiFolio asset types to Ghostfolio asset sub-classes."""
    mapping = {
        "us_equity": "STOCK",
        "cn_stock": "STOCK",
        "cn_fund": "ETF",
        "bank_wmp": "OTHER",
        "cash": "CASH"
    }
    return mapping.get(asset_type, "OTHER")

@router.get("/portfolio/details")
def ghostfolio_portfolio_details():
    """Main dashboard endpoint for Ghostfolio."""
    services = get_application_services()
    value_res = services.portfolio.get_value(base_currency="CNY")

    if not value_res.get("success"):
        return {"hasError": True, "accounts": [], "holdings": {}, "summary": {}, "platforms": []}

    data = value_res.get("data", {})
    total_value = data.get("total_value", 0.0)
    # For now we assume total investment = total value if we don't have historical cost
    total_investment = total_value

    ghost_holdings = {}
    positions = data.get("positions", {})

    for symbol, pos in positions.items():
        asset_info = services.assets.get_asset_info(symbol).get("data", {})
        asset_type = asset_info.get("asset_type", "us_equity")
        ghost_holdings[symbol] = {
            "symbol": symbol,
            "name": asset_info.get("name", symbol),
            "quantity": pos.get("shares", 0),
            "marketPrice": pos.get("price", 0),
            "currency": pos.get("currency", "CNY"),
            "allocationInPercentage": (pos.get("value", 0) / total_value) if total_value > 0 else 0,
            "performance": 0.0,
            "assetClass": map_asset_class(asset_type),
            "assetSubClass": map_asset_sub_class(asset_type)
        }

    return {
        "accounts": [],
        "holdings": ghost_holdings,
        "summary": {
            "currentNetWorth": total_value,
            "totalInvestment": total_investment,
            "grossPerformance": 0.0,
            "grossPerformancePercentage": 0.0
        },
        "platforms": [],
        "hasError": False
    }

@router.get("/portfolio/performance")
def ghostfolio_portfolio_performance():
    """Performance chart data for Ghostfolio."""
    services = get_application_services()
    value_res = services.portfolio.get_value(base_currency="CNY")
    chart_res = services.dashboard.get_performance_chart_data(days=365)

    if not value_res.get("success") or not chart_res.get("success"):
        return {"chart": [], "performance": {}}

    value_data = value_res.get("data", {})
    chart_data = chart_res.get("data", {})

    total_value = value_data.get("total_value", 0.0)

    ghost_chart = []
    dates = chart_data.get("dates", [])
    cumulative_returns = chart_data.get("cumulative_returns", [])

    for i, date_str in enumerate(dates):
        ret = cumulative_returns[i] if i < len(cumulative_returns) else 0
        ghost_chart.append({
            "date": date_str,
            "netWorth": total_value * (1 + ret),
            "netPerformanceInPercentage": ret,
            "totalInvestment": total_value,
            "value": total_value * (1 + ret)
        })

    return {
        "chart": ghost_chart,
        "performance": {
            "currentNetWorth": total_value,
            "totalInvestment": total_value,
            "grossPerformance": 0.0,
            "grossPerformancePercentage": 0.0,
            "currentValueInBaseCurrency": total_value
        }
    }

@router.get("/portfolio/holdings")
def ghostfolio_portfolio_holdings(
    symbol: Optional[str] = Query(None),
    query: Optional[str] = Query(None)
):
    """Holdings list for Ghostfolio."""
    services = get_application_services()
    value_res = services.portfolio.get_value(base_currency="CNY")

    if not value_res.get("success"):
        return []

    data = value_res.get("data", {})
    positions = data.get("positions", {})
    total_value = data.get("total_value", 0.0)

    ghost_holdings = []
    for s, pos in positions.items():
        if symbol and s != symbol:
            continue
        if query and query.lower() not in s.lower():
            continue

        asset_info = services.assets.get_asset_info(s).get("data", {})
        asset_type = asset_info.get("asset_type", "us_equity")

        ghost_holdings.append({
            "symbol": s,
            "name": asset_info.get("name", s),
            "quantity": pos.get("shares", 0),
            "marketPrice": pos.get("price", 0),
            "currency": pos.get("currency", "CNY"),
            "allocationInPercentage": (pos.get("value", 0) / total_value) if total_value > 0 else 0,
            "performance": 0.0,
            "assetClass": map_asset_class(asset_type),
            "assetSubClass": map_asset_sub_class(asset_type)
        })

    return ghost_holdings

@router.get("/portfolio/dividends")
def ghostfolio_portfolio_dividends():
    """Dividends list for Ghostfolio."""
    # Stub for now
    return []

@router.get("/portfolio/investments")
def ghostfolio_portfolio_investments():
    """Investment timeline for Ghostfolio."""
    services = get_application_services()
    value_res = services.portfolio.get_value(base_currency="CNY")
    total_value = 0.0
    if value_res.get("success"):
        total_value = value_res.get("data", {}).get("total_value", 0.0)

    from datetime import datetime
    today = datetime.now().strftime("%Y-%m-%d")

    return {
        "investments": [{"date": today, "investment": total_value}],
        "streaks": {"currentStreak": 1, "longestStreak": 1}
    }

@router.get("/portfolio/report")
def ghostfolio_portfolio_report():
    """Report stub for Ghostfolio."""
    return {"xRay": {"categories": [], "statistics": {"totalCount": 0}}}

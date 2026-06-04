"""FastAPI entrypoint for the new OptiFolio HTTP API."""

import os
from typing import Dict, List, Optional

from fastapi import FastAPI, Query
from fastapi.encoders import jsonable_encoder
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from src.services import get_application_services
from src.services.response import success


class BacktestPayload(BaseModel):
    assets: List[str] = Field(min_length=1)
    target_weights: Optional[Dict[str, float]] = None
    start: Optional[str] = None
    end: Optional[str] = None
    rebalance_frequency: str = "M"
    fee_rate: float = Field(default=0.0, ge=0.0)
    initial_cash: float = Field(default=1.0, gt=0.0)
    risk_free_rate: float = 0.0


class OptimizationPayload(BaseModel):
    assets: List[str] = Field(min_length=1)
    start: Optional[str] = None
    end: Optional[str] = None
    method: str = "mean_variance"
    objective: str = "max_sharpe"
    risk_free_rate: float = 0.02


_ERROR_CODE_STATUS = {
    "NO_PRICE_DATA": 422,
    "INVALID_OPTIMIZATION_METHOD": 400,
    "INVALID_OPTIMIZATION_OBJECTIVE": 400,
    "OPTIMIZATION_NO_DATA": 422,
    "OPTIMIZATION_INSUFFICIENT_ASSETS": 422,
    "VALUATION_ERROR": 500,
    "BACKTEST_ERROR": 500,
    "OPTIMIZATION_ERROR": 500,
    "FX_EXPOSURE_ERROR": 500,
    "CONCENTRATION_ERROR": 500,
    "LIQUIDITY_ERROR": 500,
    "GHOSTFOLIO_EXPORT_ERROR": 500,
}


def _json_response(payload: dict) -> JSONResponse:
    if payload.get("success", True):
        status_code = 200
    else:
        error_code = payload.get("error_code", "")
        status_code = _ERROR_CODE_STATUS.get(error_code, 400)
    return JSONResponse(status_code=status_code, content=jsonable_encoder(payload))


def create_app() -> FastAPI:
    app = FastAPI(
        title="OptiFolio API",
        version="0.1.0",
        description="HTTP API for OptiFolio portfolio and asset services.",
    )

    cors_origins_str = os.environ.get("CORS_ORIGINS", "")
    if cors_origins_str:
        allow_origins = [origin.strip() for origin in cors_origins_str.split(",") if origin.strip()]
    else:
        allow_origins = ["http://localhost:5173", "http://127.0.0.1:5173"]

    app.add_middleware(
        CORSMiddleware,
        allow_origins=allow_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Content-Type", "Authorization", "Accept"],
    )

    @app.get("/health", tags=["system"])
    def health() -> JSONResponse:
        return _json_response(success({"status": "ok"}, "OptiFolio API is running"))

    @app.get("/api/system/status", tags=["system"])
    def system_status() -> JSONResponse:
        return _json_response(get_application_services().system.get_status())

    @app.get("/api/dashboard/summary", tags=["dashboard"])
    def dashboard_summary(
        base_currency: Optional[str] = Query(default=None, min_length=3, max_length=3)
    ) -> JSONResponse:
        return _json_response(
            get_application_services().dashboard.get_summary(base_currency)
        )

    @app.get("/api/dashboard/asset-type-distribution", tags=["dashboard"])
    def asset_type_distribution() -> JSONResponse:
        return _json_response(
            get_application_services().dashboard.get_asset_type_distribution()
        )

    @app.get("/api/portfolio/value", tags=["portfolio"])
    def portfolio_value(
        base_currency: Optional[str] = Query(default=None, min_length=3, max_length=3)
    ) -> JSONResponse:
        return _json_response(get_application_services().portfolio.get_value(base_currency))

    @app.get("/api/portfolio/cash", tags=["portfolio"])
    def portfolio_cash() -> JSONResponse:
        return _json_response(get_application_services().portfolio.get_cash())

    @app.get("/api/portfolio/holdings", tags=["portfolio"])
    def portfolio_holdings() -> JSONResponse:
        return _json_response(get_application_services().portfolio.get_holdings())

    @app.get("/api/portfolio/v2/performance/fx-decomposition", tags=["portfolio"])
    def fx_decomposition(
        start: str = Query(..., regex=r"^\d{4}-\d{2}-\d{2}$"),
        end: str = Query(..., regex=r"^\d{4}-\d{2}-\d{2}$"),
        base_currency: Optional[str] = Query(default=None, min_length=3, max_length=3),
    ) -> JSONResponse:
        from datetime import datetime
        try:
            start_date = datetime.strptime(start, "%Y-%m-%d").date()
            end_date = datetime.strptime(end, "%Y-%m-%d").date()
            return _json_response(
                get_application_services().portfolio_v2.get_fx_decomposition(
                    start_date, end_date, base_currency
                )
            )
        except ValueError as exc:
            return _json_response({"success": False, "message": str(exc), "error_code": "INVALID_DATE_FORMAT"})

    @app.get("/api/portfolio/v2/ledger", tags=["portfolio"])
    def portfolio_ledger(
        start: Optional[str] = Query(default=None),
        end: Optional[str] = Query(default=None),
    ) -> JSONResponse:
        return _json_response(
            get_application_services().portfolio.get_ledger(start, end)
        )
    @app.get("/api/assets/overview", tags=["assets"])
    def asset_overview() -> JSONResponse:
        return _json_response(get_application_services().assets.get_overview())

    @app.get("/api/assets", tags=["assets"])
    def list_assets(
        filter_type: Optional[str] = None,
        page: int = Query(default=1, ge=1),
        page_size: int = Query(default=50, ge=1, le=200),
    ) -> JSONResponse:
        return _json_response(
            get_application_services().assets.list_assets(filter_type, page, page_size)
        )

    @app.get("/api/assets/search", tags=["assets"])
    def search_assets(
        query: str = Query(min_length=1),
        limit: int = Query(default=50, ge=1, le=200),
    ) -> JSONResponse:
        return _json_response(
            get_application_services().assets.search_assets(query, limit)
        )

    @app.get("/api/assets/{symbol}", tags=["assets"])
    def asset_info(symbol: str) -> JSONResponse:
        return _json_response(get_application_services().assets.get_asset_info(symbol))

    @app.get("/api/market/assets", tags=["market"])
    def market_assets() -> JSONResponse:
        return _json_response(get_application_services().research.list_market_assets())

    @app.get("/api/market/prices", tags=["market"])
    def market_prices(
        assets: List[str] = Query(min_length=1),
        start: Optional[str] = None,
        end: Optional[str] = None,
        field: str = "adj_close",
    ) -> JSONResponse:
        return _json_response(
            get_application_services().research.get_prices(assets, start, end, field)
        )

    @app.get("/api/market/returns", tags=["market"])
    def market_returns(
        assets: List[str] = Query(min_length=1),
        start: Optional[str] = None,
        end: Optional[str] = None,
        frequency: str = "D",
    ) -> JSONResponse:
        return _json_response(
            get_application_services().research.get_returns(assets, start, end, frequency)
        )

    @app.get("/api/market/missing-report", tags=["market"])
    def market_missing_report(
        assets: List[str] = Query(min_length=1),
        start: Optional[str] = None,
        end: Optional[str] = None,
    ) -> JSONResponse:
        return _json_response(
            get_application_services().research.get_missing_report(assets, start, end)
        )

    @app.post("/api/research/backtest", tags=["research"])
    def run_backtest(payload: BacktestPayload) -> JSONResponse:
        return _json_response(
            get_application_services().research.run_backtest(
                assets=payload.assets,
                target_weights=payload.target_weights,
                start=payload.start,
                end=payload.end,
                rebalance_frequency=payload.rebalance_frequency,
                fee_rate=payload.fee_rate,
                initial_cash=payload.initial_cash,
                risk_free_rate=payload.risk_free_rate,
            )
        )

    @app.post("/api/research/optimize", tags=["research"])
    def run_optimization(payload: OptimizationPayload) -> JSONResponse:
        return _json_response(
            get_application_services().research.run_optimization(
                assets=payload.assets,
                start=payload.start,
                end=payload.end,
                method=payload.method,
                objective=payload.objective,
                risk_free_rate=payload.risk_free_rate,
            )
        )

    # ── Portfolio V2 routes (date-aware valuation) ────────────────────

    class DividendPayload(BaseModel):
        """Request payload for recording a dividend corporate action."""
        asset_id: str = Field(min_length=1, description="Asset identifier (e.g. ticker symbol)")
        ex_date: str = Field(description="Ex-dividend date in YYYY-MM-DD format")
        amount_per_share: float = Field(gt=0, description="Dividend amount per share (must be > 0)")
        currency: str = Field(default="USD", description="ISO 4217 currency code of the dividend")
        effective_date: Optional[str] = Field(default=None, description="Date the dividend is effective in YYYY-MM-DD format; defaults to ex_date if omitted")
        withholding_tax_rate: float = Field(default=0.0, description="Withholding tax rate applied to the dividend (0.0 to 1.0)")

    class SplitPayload(BaseModel):
        asset_id: str = Field(min_length=1)
        ex_date: str  # YYYY-MM-DD
        ratio: float = Field(gt=0)
        effective_date: Optional[str] = None

    class MergerPayload(BaseModel):
        asset_id: str = Field(min_length=1)
        target_asset_id: str = Field(min_length=1)
        ex_date: str
        exchange_ratio: float = Field(gt=0)
        cash_per_share: float = 0.0
        cash_currency: str = "USD"
        effective_date: Optional[str] = None

    class GhostfolioExportPayload(BaseModel):
        host: str = Field(default="http://localhost:3333", description="Ghostfolio instance URL")
        token: str = Field(min_length=1, description="Ghostfolio JWT bearer token")
        account_name: Optional[str] = Field(default="OptiFolio", description="Ghostfolio account name")
        account_currency: Optional[str] = Field(default="USD", description="Ghostfolio account currency")
        date: Optional[str] = Field(default=None, description="Date for activities in YYYY-MM-DD (default: today)")

    @app.post("/api/portfolio/v2/export/ghostfolio", tags=["portfolio"])
    def export_to_ghostfolio(payload: GhostfolioExportPayload) -> JSONResponse:
        """Export current portfolio holdings to Ghostfolio as BUY activities.

        Pushes a portfolio snapshot to Ghostfolio by creating one BUY activity
        per holding at the current market price. Ghostfolio then tracks live
        prices and computes valuations internally.

        Returns ``{"success": true, "data": {"activities_imported": 12}}``.
        """
        from tools.export_to_ghostfolio import (
            GhostfolioExporter,
            load_latest_prices,
            load_portfolio,
        )
        from src.data_foundation.repository import MarketDataRepository
        from datetime import date

        holdings, cash = load_portfolio()
        if not holdings:
            return _json_response({
                "success": True,
                "data": {"activities_imported": 0},
                "message": "No holdings to export.",
            })

        repo = MarketDataRepository()
        prices = load_latest_prices(holdings, repo)

        exporter = GhostfolioExporter(payload.host, payload.token)
        date_str = payload.date or date.today().isoformat()

        try:
            account_id = exporter.get_or_create_account(
                payload.account_name or "OptiFolio",
                payload.account_currency or "USD",
            )
            count = exporter.export_holdings(
                holdings, cash, prices, date_str,
                account_id=account_id,
                account_name=payload.account_name or "OptiFolio",
                account_currency=payload.account_currency or "USD",
            )
        except Exception as exc:
            return _json_response({
                "success": False,
                "message": str(exc),
                "error_code": "GHOSTFOLIO_EXPORT_ERROR",
            })

        return _json_response({
            "success": True,
            "data": {"activities_imported": count},
            "message": f"{count} activities exported to Ghostfolio",
        })

    @app.get("/api/portfolio/v2/value", tags=["portfolio"])
    def portfolio_v2_value(
        as_of: Optional[str] = Query(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$"),
        base_currency: Optional[str] = Query(default=None, min_length=3, max_length=3),
    ) -> JSONResponse:
        """Date-aware portfolio valuation (next-day NAV).

        Returns the total portfolio value as of the requested date, along with
        per-position and per-currency breakdowns.

        Metadata in the response:
        - ``price_date``: the actual date of the prices used for valuation (the most
          recent available price on or before ``as_of``). This may differ from ``as_of``
          when the latest market data is not yet available.
        - ``stale_days``: the number of days between ``as_of`` and ``price_date``
          (computed as ``as_of - price_date``). A value of 0 means prices are
          up-to-date; larger values indicate stale data that the frontend should
          surface to the user.
        """
        from datetime import date as date_cls
        as_of_date = date_cls.fromisoformat(as_of) if as_of else None
        return _json_response(
            get_application_services().portfolio_v2.get_value(
                as_of=as_of_date, base_currency=base_currency,
            )
        )

    @app.get("/api/portfolio/v2/history", tags=["portfolio"])
    def portfolio_v2_history(
        start: str = Query(pattern=r"^\d{4}-\d{2}-\d{2}$"),
        end: str = Query(pattern=r"^\d{4}-\d{2}-\d{2}$"),
        base_currency: Optional[str] = Query(default=None, min_length=3, max_length=3),
    ) -> JSONResponse:
        """Daily portfolio valuation over a date range."""
        from datetime import date as date_cls
        return _json_response(
            get_application_services().portfolio_v2.get_value_history(
                start=date_cls.fromisoformat(start),
                end=date_cls.fromisoformat(end),
                base_currency=base_currency,
            )
        )

    @app.get("/api/portfolio/v2/holdings", tags=["portfolio"])
    def portfolio_v2_holdings() -> JSONResponse:
        return _json_response(
            get_application_services().portfolio_v2.get_current_holdings()
        )

    @app.get("/api/portfolio/v2/cash", tags=["portfolio"])
    def portfolio_v2_cash() -> JSONResponse:
        return _json_response(
            get_application_services().portfolio_v2.get_cash_balances()
        )

    @app.get("/api/portfolio/v2/corporate-actions", tags=["portfolio"])
    def portfolio_v2_corporate_actions(
        asset_id: Optional[str] = None,
    ) -> JSONResponse:
        return _json_response(
            get_application_services().portfolio_v2.get_corporate_actions(
                asset_id=asset_id,
            )
        )

    @app.post("/api/portfolio/v2/corporate-actions/dividend", tags=["portfolio"])
    def portfolio_v2_record_dividend(payload: DividendPayload) -> JSONResponse:
        """Record a dividend corporate action.

        Example success response:
        ``{"success": true, "data": {"asset_id": "AAPL", "ex_date": "2025-06-15",
        "amount_per_share": 0.50, "action": "dividend"}, "message": "Dividend recorded"}``
        """
        from datetime import date as date_cls
        return _json_response(
            get_application_services().portfolio_v2.record_dividend(
                asset_id=payload.asset_id,
                ex_date=date_cls.fromisoformat(payload.ex_date),
                amount_per_share=payload.amount_per_share,
                currency=payload.currency,
                effective_date=date_cls.fromisoformat(payload.effective_date) if payload.effective_date else None,
                withholding_tax_rate=payload.withholding_tax_rate,
            )
        )

    @app.post("/api/portfolio/v2/corporate-actions/split", tags=["portfolio"])
    def portfolio_v2_record_split(payload: SplitPayload) -> JSONResponse:
        """Record a stock split corporate action.

        Example success response:
        ``{"success": true, "data": {"asset_id": "AAPL", "ex_date": "2025-06-15",
        "ratio": 4.0, "action": "split"}, "message": "Split recorded"}``
        """
        from datetime import date as date_cls
        return _json_response(
            get_application_services().portfolio_v2.record_split(
                asset_id=payload.asset_id,
                ex_date=date_cls.fromisoformat(payload.ex_date),
                ratio=payload.ratio,
                effective_date=date_cls.fromisoformat(payload.effective_date) if payload.effective_date else None,
            )
        )

    @app.post("/api/portfolio/v2/corporate-actions/merger", tags=["portfolio"])
    def portfolio_v2_record_merger(payload: MergerPayload) -> JSONResponse:
        """Record a merger corporate action.

        Example success response:
        ``{"success": true, "data": {"asset_id": "AAPL", "target_asset_id": "GOOGL",
        "ex_date": "2025-06-15", "exchange_ratio": 0.5, "action": "merger"},
        "message": "Merger recorded"}``
        """
        from datetime import date as date_cls
        return _json_response(
            get_application_services().portfolio_v2.record_merger(
                asset_id=payload.asset_id,
                target_asset_id=payload.target_asset_id,
                ex_date=date_cls.fromisoformat(payload.ex_date),
                exchange_ratio=payload.exchange_ratio,
                cash_per_share=payload.cash_per_share,
                cash_currency=payload.cash_currency,
                effective_date=date_cls.fromisoformat(payload.effective_date) if payload.effective_date else None,
            )
        )

    @app.get("/api/portfolio/v2/metrics", tags=["portfolio"])
    def portfolio_v2_metrics() -> JSONResponse:
        return _json_response(
            get_application_services().portfolio_v2.compute_metrics()
        )

    @app.get("/api/portfolio/v2/risk/fx-exposure", tags=["portfolio"])
    def portfolio_v2_fx_exposure(
        as_of: Optional[str] = Query(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$"),
        base_currency: Optional[str] = Query(default=None, min_length=3, max_length=3),
    ) -> JSONResponse:
        """FX exposure analysis — per-currency breakdown with sensitivity estimates.

        Returns each currency's share of total portfolio value, a net non-base
        currency percentage, and warnings when thresholds are exceeded.

        Sensitivity note format: ``USD/CNY ±1% → 净值波动约 ¥1,234.56``
        """
        from datetime import date as date_cls
        as_of_date = date_cls.fromisoformat(as_of) if as_of else None
        return _json_response(
            get_application_services().portfolio_v2.get_fx_exposure_report(
                as_of=as_of_date, base_currency=base_currency,
            )
        )

    @app.get("/api/portfolio/v2/risk/concentration", tags=["portfolio"])
    def portfolio_v2_concentration(
        as_of: Optional[str] = Query(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$"),
        base_currency: Optional[str] = Query(default=None, min_length=3, max_length=3),
    ) -> JSONResponse:
        """Concentration risk analysis — breakdowns by currency, asset class, and issuer.

        Returns percentage breakdowns of portfolio value along three axes:
        - by_currency: value grouped by denomination currency
        - by_asset_class: value grouped by mapped asset class (equity, fund, bond, etc.)
        - by_issuer: value grouped by issuer/manager name

        Includes warnings in Chinese when thresholds are breached:
        - Single currency > 80%
        - Single issuer > 30%
        - Equity allocation > 70%
        """
        from datetime import date as date_cls
        as_of_date = date_cls.fromisoformat(as_of) if as_of else None
        return _json_response(
            get_application_services().portfolio_v2.get_concentration_report(
                as_of=as_of_date, base_currency=base_currency,
            )
        )

    @app.get("/api/portfolio/v2/risk/liquidity", tags=["portfolio"])
    def portfolio_v2_liquidity(
        as_of: Optional[str] = Query(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$"),
        base_currency: Optional[str] = Query(default=None, min_length=3, max_length=3),
    ) -> JSONResponse:
        """Liquidity risk analysis — portfolio value by redemption timeline.

        Classifies every position into a liquidity bucket (T+0, T+1, T+2~T+4,
        7天内, 1个月内, 3个月内, 1年内, 锁仓) using product metadata, symbol-pattern
        heuristics, and lockup dates.

        Returns:
        - buckets: ordered list with name, value, pct, asset_ids for each bucket
        - available_7d_pct: percentage of portfolio available within 7 days
        - locked_pct: percentage locked long-term (锁仓)
        """
        from datetime import date as date_cls
        as_of_date = date_cls.fromisoformat(as_of) if as_of else None
        return _json_response(
            get_application_services().portfolio_v2.get_liquidity_report(
                as_of=as_of_date, base_currency=base_currency,
            )
        )

    class RiskRulesPayload(BaseModel):
        """Request body for the risk rules endpoint — all fields are optional."""
        user_targets: Optional[Dict[str, float]] = Field(
            default=None,
            description="User-configured thresholds. Keys: emergency_months, monthly_spending, fx_target_pct",
        )

    @app.post("/api/portfolio/v2/risk/rules", tags=["portfolio"])
    def portfolio_v2_risk_rules(
        payload: RiskRulesPayload = RiskRulesPayload(),
    ) -> JSONResponse:
        """Run the risk rule engine across all dimensions.

        Accepts an optional user_targets dict to control thresholds:
        - ``emergency_months``: months of spending to cover (default 6)
        - ``monthly_spending``: monthly spending in base currency (default 0 = skip)
        - ``fx_target_pct``: max non-base currency exposure % (default 20)

        Returns each rule's result (pass/fail, severity, recommendation) plus
        an aggregate summary with counts by severity and category.
        """
        return _json_response(
            get_application_services().portfolio_v2.get_risk_rules(
                user_targets=payload.user_targets,
            )
        )

    @app.get("/api/portfolio/v2/history-entries", tags=["portfolio"])
    def portfolio_v2_history_entries(
        start: Optional[str] = Query(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$"),
        end: Optional[str] = Query(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$"),
    ) -> JSONResponse:
        from datetime import date as date_cls
        return _json_response(
            get_application_services().portfolio_v2.get_history(
                start=date_cls.fromisoformat(start) if start else None,
                end=date_cls.fromisoformat(end) if end else None,
            )
        )

    return app


app = create_app()

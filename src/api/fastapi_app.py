"""FastAPI entrypoint for the new OptiFolio HTTP API."""

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


def _json_response(payload: dict) -> JSONResponse:
    status_code = 200 if payload.get("success", True) else 500
    return JSONResponse(status_code=status_code, content=jsonable_encoder(payload))


def create_app() -> FastAPI:
    app = FastAPI(
        title="OptiFolio API",
        version="0.1.0",
        description="HTTP API for OptiFolio portfolio and asset services.",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
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

    return app


app = create_app()

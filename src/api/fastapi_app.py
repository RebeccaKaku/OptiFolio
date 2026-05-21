"""FastAPI entrypoint for the new OptiFolio HTTP API."""

import os
from typing import Optional

from fastapi import FastAPI, Query
from fastapi.encoders import jsonable_encoder
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from src.services import get_application_services
from src.services.response import success


def _json_response(payload: dict) -> JSONResponse:
    status_code = 200 if payload.get("success", True) else 500
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
        allow_methods=["GET", "OPTIONS"],
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

    return app


app = create_app()

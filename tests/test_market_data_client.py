import json

import httpx
import pytest

from src.infrastructure.market_data_client import (
    DataNotAvailableError,
    DataServiceUnavailableError,
    HttpMarketDataClient,
)


def _json(payload, status=200):
    return httpx.Response(status, json=payload)


def test_price_matrix_decodes_remote_records():
    def handler(request: httpx.Request):
        assert request.headers["authorization"] == "Bearer token"
        return _json({"data": [
            {"date": "2026-06-01T00:00:00", "equity.us.aapl": 100.0},
            {"date": "2026-06-02T00:00:00", "equity.us.aapl": 101.0},
        ]})
    client = HttpMarketDataClient(token="token", transport=httpx.MockTransport(handler))
    frame = client.get_prices(["equity.us.aapl"])
    assert list(frame["equity.us.aapl"]) == [100.0, 101.0]


def test_missing_price_registers_asset():
    requests = []
    def handler(request: httpx.Request):
        requests.append((request.method, request.url.path))
        if request.url.path == "/v1/prices":
            return _json({"detail": {"code": "NO_DATA"}}, 404)
        return _json({"data": {"job_id": "job-1", "status": "queued"}}, 202)
    client = HttpMarketDataClient(token="token", transport=httpx.MockTransport(handler))
    assert client.get_prices(["equity.us.aapl"]).empty
    assert requests == [("GET", "/v1/prices"), ("POST", "/v1/assets/ensure")]


def test_sparse_batch_registers_only_missing_asset():
    requests = []

    def handler(request: httpx.Request):
        requests.append((request.method, request.url.path))
        if request.url.path == "/v1/prices":
            return _json({"data": [{
                "date": "2026-06-27T00:00:00",
                "equity.us.aapl": 100.0,
                "equity.us.qqq": None,
            }]})
        payload = json.loads(request.content)
        assert payload["asset_id"] == "equity.us.qqq"
        return _json({"data": {"job_id": "job-1", "status": "queued"}}, 202)

    client = HttpMarketDataClient(token="token", transport=httpx.MockTransport(handler))
    frame = client.get_prices(["equity.us.aapl", "equity.us.qqq"])
    assert frame["equity.us.aapl"].iloc[0] == 100.0
    assert requests == [("GET", "/v1/prices"), ("POST", "/v1/assets/ensure")]


def test_blank_currency_is_rejected_locally():
    client = HttpMarketDataClient(token="token")
    with pytest.raises(DataNotAvailableError, match="INVALID_CURRENCY"):
        client.fx_rate("", "CNY")


def test_transport_failure_has_no_local_fallback():
    def handler(_request: httpx.Request):
        raise httpx.ConnectError("offline")
    client = HttpMarketDataClient(token="token", transport=httpx.MockTransport(handler))
    with pytest.raises(DataServiceUnavailableError):
        client.list_assets()


def test_api_maps_provider_outage_to_503():
    from src.api.fastapi_app import _json_response

    response = _json_response({
        "success": False,
        "message": "FinDataProvider unavailable at http://127.0.0.1:8020",
        "error_code": "PRICE_MATRIX_ERROR",
    })
    assert response.status_code == 503
    assert json.loads(response.body)["error_code"] == "DATA_SERVICE_UNAVAILABLE"

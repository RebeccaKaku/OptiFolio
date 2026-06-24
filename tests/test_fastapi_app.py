from types import SimpleNamespace

from fastapi.testclient import TestClient

from src.api import fastapi_app


def test_health_endpoint_does_not_require_services():
    client = TestClient(fastapi_app.create_app())

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["success"] is True
    assert response.json()["data"]["status"] == "ok"


def test_portfolio_value_route_uses_service_layer(monkeypatch):
    class FakePortfolioService:
        def get_value(self, as_of=None, base_currency=None):
            return {
                "success": True,
                "data": {"base_currency": base_currency, "total_value": 123.45},
                "message": "fake portfolio",
            }

    fake_services = SimpleNamespace(portfolio=FakePortfolioService())
    monkeypatch.setattr(fastapi_app, "get_application_services", lambda: fake_services)
    client = TestClient(fastapi_app.create_app())

    response = client.get("/api/portfolio/value?base_currency=USD")

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["data"]["base_currency"] == "USD"


def test_asset_list_validates_page_size_before_service_call(monkeypatch):
    fake_services = SimpleNamespace(assets=object())
    monkeypatch.setattr(fastapi_app, "get_application_services", lambda: fake_services)
    client = TestClient(fastapi_app.create_app())

    response = client.get("/api/assets?page_size=0")

    assert response.status_code == 422


def test_research_backtest_route_uses_service_layer(monkeypatch):
    class FakeResearchService:
        def run_backtest(self, **kwargs):
            return {
                "success": True,
                "data": {"assets": kwargs["assets"], "metrics": {"total_return": 0.1}},
                "message": "fake backtest",
            }

    fake_services = SimpleNamespace(research=FakeResearchService())
    monkeypatch.setattr(fastapi_app, "get_application_services", lambda: fake_services)
    client = TestClient(fastapi_app.create_app())

    response = client.post("/api/research/backtest", json={"assets": ["AAA", "BBB"]})

    assert response.status_code == 200
    assert response.json()["data"]["assets"] == ["AAA", "BBB"]


def test_market_prices_route_uses_service_layer(monkeypatch):
    class FakeResearchService:
        def get_prices(self, assets, start, end, field):
            return {
                "success": True,
                "data": {"assets": assets, "start": start, "end": end, "field": field, "prices": {assets[0]: {}}},
                "message": "fake prices",
            }

    fake_services = SimpleNamespace(research=FakeResearchService())
    monkeypatch.setattr(fastapi_app, "get_application_services", lambda: fake_services)
    client = TestClient(fastapi_app.create_app())

    response = client.get("/api/market/prices?assets=AAPL&start=2024-01-01&end=2024-01-10")

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["data"]["assets"] == ["AAPL"]
    assert payload["data"]["start"] == "2024-01-01"
    assert payload["data"]["end"] == "2024-01-10"


def test_market_prices_empty_assets_fails(monkeypatch):
    client = TestClient(fastapi_app.create_app())
    response = client.get("/api/market/prices")
    # It should fail validation because min_length=1 (default is None/missing which fails)
    assert response.status_code == 422


def test_market_prices_invalid_date_range_is_passed_to_service(monkeypatch):
    class FakeResearchService:
        def get_prices(self, assets, start, end, field):
            return {
                "success": True,
                "data": {"start": start, "end": end},
                "message": "fake prices",
            }

    fake_services = SimpleNamespace(research=FakeResearchService())
    monkeypatch.setattr(fastapi_app, "get_application_services", lambda: fake_services)
    client = TestClient(fastapi_app.create_app())

    # Send reversed dates
    response = client.get("/api/market/prices?assets=AAPL&start=2024-02-01&end=2024-01-01")

    assert response.status_code == 200
    payload = response.json()
    assert payload["data"]["start"] == "2024-02-01"
    assert payload["data"]["end"] == "2024-01-01"

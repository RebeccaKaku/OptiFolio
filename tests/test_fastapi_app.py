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
        def get_value(self, base_currency=None):
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


def test_list_alerts_returns_empty_list_by_default(monkeypatch):
    class FakeAlertEngine:
        def run_all(self, **kwargs):
            return []

    fake_services = SimpleNamespace(alerts=FakeAlertEngine())
    monkeypatch.setattr(fastapi_app, "get_application_services", lambda: fake_services)
    client = TestClient(fastapi_app.create_app())

    response = client.get("/api/alerts")

    assert response.status_code == 200
    assert response.json()["success"] is True
    assert response.json()["data"] == []


def test_run_alerts_with_context(monkeypatch):
    from src.analytics.alerts import Alert

    class FakeAlertEngine:
        def run_all(self, **context):
            if context.get("quality_summary", {}).get("stale_assets") == ["AAPL"]:
                return [Alert(
                    alert_id="stale_price_threshold",
                    title="Stale prices detected",
                    reason="AAPL is stale",
                    evidence=context["quality_summary"],
                    severity="warning",
                    suggested_action="Fix it",
                    created_at="2023-01-01T00:00:00Z"
                )]
            return []

    fake_services = SimpleNamespace(alerts=FakeAlertEngine())
    monkeypatch.setattr(fastapi_app, "get_application_services", lambda: fake_services)
    client = TestClient(fastapi_app.create_app())

    payload = {
        "quality_summary": {
            "threshold_pct": 50.0,
            "stale_assets": ["AAPL"],
            "n_days": 5
        }
    }
    response = client.post("/api/alerts/run", json=payload)

    assert response.status_code == 200
    data = response.json()["data"]
    assert len(data) == 1
    assert data[0]["alert_id"] == "stale_price_threshold"
    assert data[0]["evidence"]["stale_assets"] == ["AAPL"]

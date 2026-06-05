import pytest
from datetime import date
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient
from src.api.fastapi_app import create_app
from src.services.application import ApplicationServices, get_application_services
from src.domain.models import ValuationResult, PositionValue, CashHolding

@pytest.fixture
def client():
    app = create_app()
    return TestClient(app)

def test_fx_decomposition_integration():
    # Setup mock data
    start_date = date(2026, 1, 1)
    end_date = date(2026, 6, 1)

    # Mock ValuationResults
    # Initial: 100 shares of AAPL @ 150 USD, USD/CNY = 7.0
    # Final: 100 shares of AAPL @ 160 USD, USD/CNY = 7.2

    val_start = ValuationResult(
        as_of=start_date,
        total_value=105000.0,
        holdings_value=105000.0,
        cash_value=0.0,
        base_currency="CNY",
        positions={
            "AAPL": PositionValue(
                asset_id="AAPL", quantity=100, price=150.0, currency="USD",
                fx_rate=7.0, value_base=105000.0, price_date=start_date
            )
        },
        fx_rates={"USD": 7.0}
    )

    val_end = ValuationResult(
        as_of=end_date,
        total_value=115200.0,
        holdings_value=115200.0,
        cash_value=0.0,
        base_currency="CNY",
        positions={
            "AAPL": PositionValue(
                asset_id="AAPL", quantity=100, price=160.0, currency="USD",
                fx_rate=7.2, value_base=115200.0, price_date=end_date
            )
        },
        fx_rates={"USD": 7.2}
    )

    with patch("src.services.portfolio_service_v2.PortfolioServiceV2._load_portfolio"), \
         patch("src.services.portfolio_service_v2.ValuationEngine.value") as mock_value, \
         patch("src.services.portfolio_service_v2.CorporateActionProcessor.apply_to_holdings") as mock_apply:

        mock_apply.return_value = ({}, {}, [])
        mock_value.side_effect = [val_start, val_end]

        from src.services.application import get_application_services
        svc = get_application_services().portfolio_v2

        # Test Service Method
        response = svc.get_fx_decomposition(start_date, end_date, "CNY")

        assert response["success"] is True
        data = response["data"]
        assert data["base_currency"] == "CNY"
        assert data["start_value"] == 105000.0
        assert data["end_value"] == 115200.0

        # total_return = 115200/105000 - 1 = 0.097143
        # local_return = 160/150 - 1 = 0.066667
        # fx_return = 7.2/7.0 - 1 = 0.028571
        # interaction = 0.066667 * 0.028571 = 0.001905
        # sum = 0.066667 + 0.028571 + 0.001905 = 0.097143

        assert pytest.approx(data["total_return"], 0.000001) == 0.097143
        assert pytest.approx(data["local_return"], 0.000001) == 0.066667
        assert pytest.approx(data["fx_return"], 0.000001) == 0.028571

        assert "USD" in data["per_currency"]
        usd_data = data["per_currency"]["USD"]
        assert pytest.approx(usd_data["local_return"], 0.000001) == 0.066667
        assert pytest.approx(usd_data["fx_return"], 0.000001) == 0.028571

def test_fx_decomposition_api(client):
    start_str = "2026-01-01"
    end_str = "2026-06-01"

    with patch("src.services.portfolio_service_v2.PortfolioServiceV2.get_fx_decomposition") as mock_decomp:
        mock_decomp.return_value = {
            "success": True,
            "data": {
                "base_currency": "CNY",
                "start_value": 600000.0,
                "end_value": 673444.0,
                "total_return": 0.1224,
                "local_return": 0.0950,
                "fx_return": 0.0250,
                "interaction": 0.0024,
                "per_currency": {
                    "USD": {"local_return": 0.08, "fx_return": 0.025, "weight": 0.45}
                }
            }
        }

        response = client.get(f"/api/portfolio/v2/performance/fx-decomposition?start={start_str}&end={end_str}&base_currency=CNY")

        assert response.status_code == 200
        json_data = response.json()
        assert json_data["success"] is True
        assert json_data["data"]["total_return"] == 0.1224
        assert json_data["data"]["per_currency"]["USD"]["local_return"] == 0.08

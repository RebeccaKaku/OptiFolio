import pytest
from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock

from src.core.portfolio_book_db import PortfolioBookDatabase
from src.services.my_money_service import MyMoneyService
from src.services.book_valuation_service import BookValuationService

@pytest.fixture
def mock_db():
    db = MagicMock(spec=PortfolioBookDatabase)
    return db

@pytest.fixture
def mock_val_svc():
    svc = MagicMock(spec=BookValuationService)
    return svc

@pytest.fixture
def mock_provider():
    provider = MagicMock()
    return provider

def test_get_summary_no_data(mock_db, mock_val_svc, mock_provider):
    mock_db.get_latest_confirmed_batch.return_value = None
    service = MyMoneyService(mock_db, mock_val_svc, mock_provider)

    res = service.get_summary()
    assert res["success"] is True
    assert res["data"]["has_data"] is False

def test_get_summary_with_data(mock_db, mock_val_svc, mock_provider):
    # Setup latest batch
    mock_db.get_latest_confirmed_batch.return_value = {
        "batch_id": "b1",
        "as_of": "2026-06-15",
        "status": "confirmed",
        "account_coverage": []
    }

    # Setup valuation results
    mock_val_svc.value_batch.return_value = {
        "success": True,
        "data": {
            "valuations": [
                {
                    "account_id": "acc1",
                    "product_id": "p1",
                    "amount": 1000.0,
                    "currency": "CNY",
                    "valuation_date": "2026-06-15",
                    "known_at": "2026-06-15",
                    "source_type": "manual",
                    "source_id": "b1",
                    "quality": "confirmed",
                    "freshness": "current",
                    "is_estimate": False,
                    "age_days": 0,
                    "warnings": []
                }
            ]
        }
    }

    # Setup FX
    mock_provider.fx_rate.return_value = 7.2

    # Setup previous batch for reconciliation
    mock_db.get_previous_confirmed_batch.return_value = None

    service = MyMoneyService(mock_db, mock_val_svc, mock_provider)
    res = service.get_summary(reporting_currency="CNY")

    assert res["success"] is True
    assert res["data"]["has_data"] is True
    assert res["data"]["total_assets_reporting"] == 1000.0
    assert res["data"]["return_status"] == "unavailable"

def test_get_summary_dual_currency(mock_db, mock_val_svc, mock_provider):
    mock_db.get_latest_confirmed_batch.return_value = {
        "batch_id": "b1",
        "as_of": "2026-06-15",
        "status": "confirmed",
        "account_coverage": []
    }

    mock_val_svc.value_batch.return_value = {
        "success": True,
        "data": {
            "valuations": [
                {
                    "account_id": "acc1",
                    "product_id": "p1",
                    "amount": 100.0,
                    "currency": "USD",
                    "valuation_date": "2026-06-15",
                    "known_at": "2026-06-15",
                    "source_type": "manual",
                    "source_id": "b1",
                    "quality": "confirmed",
                    "freshness": "current",
                    "is_estimate": False,
                    "age_days": 0,
                    "warnings": []
                }
            ]
        }
    }

    mock_provider.fx_rate.side_effect = lambda f, t, **kwargs: 7.0 if f=="USD" and t=="CNY" else 1.0
    mock_db.get_previous_confirmed_batch.return_value = None

    service = MyMoneyService(mock_db, mock_val_svc, mock_provider)
    res = service.get_summary(reporting_currency="CNY")

    assert res["success"] is True
    assert res["data"]["total_assets_reporting"] == 700.0
    assert res["data"]["usd_total"] == 100.0
    assert "USD" in res["data"]["by_currency"]

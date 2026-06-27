"""Integration tests for FX consumption through the market-data gateway."""

from datetime import date

import pandas as pd
import pytest

from src.core.valuation import FxRateProvider, ValuationEngine
from src.domain import ValuationRequest
from tests.fakes import InMemoryMarketDataGateway


def _seed(repo: InMemoryMarketDataGateway) -> None:
    repo.save_canonical(
        pd.DataFrame({"date": ["2025-06-02", "2025-06-03", "2025-06-04"], "close": [7.1848, 7.1763, 7.1886]}),
        asset_id="fx.usd_cny.spot",
    )


def test_fx_provider_reads_canonical_gateway_rate():
    gateway = InMemoryMarketDataGateway()
    _seed(gateway)
    rate = FxRateProvider(market_data=gateway).get_rate_from_repository("USD", "CNY", date(2025, 6, 3))
    assert rate == pytest.approx(7.1763, rel=1e-4)


def test_valuation_engine_uses_canonical_fx_for_cny_base():
    gateway = InMemoryMarketDataGateway()
    _seed(gateway)
    gateway.save_canonical(
        pd.DataFrame({"date": ["2025-06-02", "2025-06-03", "2025-06-04"], "close": [100.0, 100.0, 100.0]}),
        asset_id="equity.us.aapl",
    )
    result = ValuationEngine(market_data=gateway).value(
        {"equity.us.aapl": 10}, {"USD": 0},
        ValuationRequest(as_of=date(2025, 6, 3), base_currency="CNY"),
    )
    assert result.total_value == pytest.approx(10 * 100.0 * 7.1763, rel=1e-4)

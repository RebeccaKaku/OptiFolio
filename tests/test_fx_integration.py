"""Integration tests for the unified FX data flow.

Ensures that FX rates are stored, queried, and consumed under canonical IDs
(e.g. ``fx.usd_cny.spot``) across ``findata`` and ``src.core.valuation``.
"""
from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from findata import fd
from findata.store import MarketDataRepository, CanonicalStore
from src.core.valuation import FxRateProvider, ValuationEngine
from src.domain import ValuationRequest


def _seed_usd_cny(repo: MarketDataRepository) -> None:
    """Seed a few days of USD/CNY rates under the canonical FX id."""
    df = pd.DataFrame({
        "date": ["2025-06-02", "2025-06-03", "2025-06-04"],
        "close": [7.1848, 7.1763, 7.1886],
    })
    repo.save_canonical(df, asset_id="fx.usd_cny.spot", source="test", currency="CNY")


def test_findata_serves_canonical_fx_rate(tmp_path):
    """``fd.fx_rate`` reads rates stored under ``fx.usd_cny.spot``."""
    store = CanonicalStore(root_dir=str(tmp_path))
    _seed_usd_cny(store.repo)

    provider = fd._provider_ref
    provider._store = store

    rate = provider.fx_rate("USD", "CNY", date_str="2025-06-03")
    assert rate == pytest.approx(7.1763, rel=1e-4)


def test_valuation_fx_provider_reads_canonical_fx(tmp_path):
    """``FxRateProvider`` resolves USD->CNY from the canonical store."""
    repo = MarketDataRepository(tmp_path)
    _seed_usd_cny(repo)

    fx = FxRateProvider(market_data=repo)
    rate = fx.get_rate_from_repository("USD", "CNY", date(2025, 6, 3))
    assert rate == pytest.approx(7.1763, rel=1e-4)


def test_valuation_engine_uses_canonical_fx_for_cny_base(tmp_path):
    """A USD asset valued in CNY uses the canonical USD/CNY rate."""
    repo = MarketDataRepository(tmp_path)
    _seed_usd_cny(repo)

    df = pd.DataFrame({
        "date": ["2025-06-02", "2025-06-03", "2025-06-04"],
        "close": [100.0, 100.0, 100.0],
    })
    repo.save_canonical(df, asset_id="equity.us.aapl", source="test", currency="USD")

    engine = ValuationEngine(market_data=repo)
    result = engine.value(
        {"equity.us.aapl": 10},
        {"USD": 0},
        ValuationRequest(as_of=date(2025, 6, 3), base_currency="CNY"),
    )
    assert result.total_value == pytest.approx(10 * 100.0 * 7.1763, rel=1e-4)


def test_sync_fx_rates_stores_canonical_id(tmp_path, monkeypatch):
    """``tools/sync_fx_rates.sync_pair`` delegates to fd.fx_rate via findata."""
    from findata import fd
    from tools import sync_fx_rates

    repo = MarketDataRepository(tmp_path)

    # Mock fd.fx_rate to avoid network calls — sync_pair now delegates
    # to findata instead of calling akshare directly.
    monkeypatch.setattr(fd, "fx_rate", lambda *a, **kw: 7.18)

    rows = sync_fx_rates.sync_pair(
        "USDCNY", "美元", "USD", "CNY",
        "20250601", "20250603", repo,
    )
    assert rows == 1


def test_no_legacy_fx_ids_in_active_store(tmp_path):
    """After migration, canonical store must not contain ``FX_*`` assets."""
    repo = MarketDataRepository(tmp_path)
    _seed_usd_cny(repo)
    assets = repo.list_assets()
    legacy = [a for a in assets if a.startswith("FX_")]
    assert not legacy, f"legacy FX IDs found: {legacy}"

import pytest
import pandas as pd
from FinData.adapters.us_equity import UsEquityFetcher
from FinData.adapters.cn_stock import CnStockFetcher
from FinData.adapters.forex import CurrencyFetcher
from FinData.serving.provider import DataProvider

@pytest.mark.live
def test_us_equity_fetcher_aapl():
    """UsEquityFetcher smoke test: fetch AAPL, verify close in $200-$400 range, O<=H, L<=C, volume>0."""
    fetcher = UsEquityFetcher()
    # Confirmed 2026-06-18: AAPL=$299.24
    end_date = "2026-06-19"
    start_date = "2026-06-10"

    result = fetcher.fetch("AAPL", start_date=start_date, end_date=end_date)
    assert result.success, f"UsEquityFetcher failed: {result.errors}"
    df = result.data
    assert df is not None and not df.empty, "No data returned for AAPL"

    last_row = df.iloc[-1]
    close = last_row["close"]
    assert 200 <= close <= 400, f"AAPL close {close} out of range [200, 400]"
    assert last_row["volume"] > 0, "AAPL volume should be positive"

    # OHLCV relationship tests
    # Sina columns: open, high, low, close
    for _, row in df.iterrows():
        assert row["low"] <= row["open"] <= row["high"], f"Invalid OH relationship: {row.to_dict()}"
        assert row["low"] <= row["close"] <= row["high"], f"Invalid CH relationship: {row.to_dict()}"


@pytest.mark.live
def test_cn_stock_fetcher_600519():
    """CnStockFetcher smoke test: fetch 600519, verify close in ¥800-¥2500, O<=H, L<=C."""
    fetcher = CnStockFetcher()
    # Confirmed 2026-06-18: 600519 is in range
    end_date = "2026-06-19"
    start_date = "2026-06-10"

    result = fetcher.fetch("600519", start_date=start_date, end_date=end_date)
    assert result.success, f"CnStockFetcher failed: {result.errors}"
    df = result.data
    assert df is not None and not df.empty, "No data returned for 600519"

    last_row = df.iloc[-1]
    close = last_row["Close"]
    assert 800 <= close <= 2500, f"600519 close {close} out of range [800, 2500]"

    # OHLCV relationship tests
    # Standardized columns: Open, High, Low, Close
    for _, row in df.iterrows():
        assert row["Low"] <= row["Open"] <= row["High"], f"Invalid OH relationship: {row.to_dict()}"
        assert row["Low"] <= row["Close"] <= row["High"], f"Invalid CH relationship: {row.to_dict()}"


@pytest.mark.live
def test_currency_fetcher_usdcny():
    """CurrencyFetcher smoke test: fetch USD/CNY, verify in 6.0-8.0 range."""
    fetcher = CurrencyFetcher()
    # Confirmed 2026-06-18: USD/CNY=7.30
    end_date = "2026-06-19"
    start_date = "2026-06-10"

    df = fetcher.fetch("USDCNY", start_date=start_date, end_date=end_date)
    assert df is not None and not df.empty, "No data returned for USDCNY"

    close = df["Close"].iloc[-1]
    assert 6.0 <= close <= 8.0, f"USDCNY rate {close} out of range [6.0, 8.0]"

    # OHLCV relationship tests
    for _, row in df.iterrows():
        if pd.notna(row["High"]) and pd.notna(row["Low"]):
            if pd.notna(row["Open"]):
                assert row["Low"] <= row["Open"] <= row["High"], f"Invalid OH relationship: {row.to_dict()}"
            assert row["Low"] <= row["Close"] <= row["High"], f"Invalid CH relationship: {row.to_dict()}"


@pytest.mark.live
def test_stored_shibor_rate():
    """Rate validation test: verify stored SHIBOR 1Y rate is in 0.5%-5% range."""
    provider = DataProvider()
    # Check rate as of confirmed date
    rate_info = provider.rate("1y_cn", date_str="2026-06-18")

    # Value should be in decimal, e.g., 0.0146 for 1.46%
    value = rate_info["value"]
    # 0.5% - 5% range -> 0.005 - 0.05
    assert 0.005 <= value <= 0.05, f"SHIBOR 1Y rate {value} out of range [0.005, 0.05]"

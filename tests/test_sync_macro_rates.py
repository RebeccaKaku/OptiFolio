from __future__ import annotations

import pandas as pd
import pytest

from tools.sync_macro_rates import (
    FredRateSpec,
    InterbankSpec,
    PolicyRateSpec,
    _filter_dates,
    macro_series_catalog,
    normalize_fred_rate_frame,
    normalize_interbank_frame,
    normalize_policy_rate_frame,
)


def test_normalize_interbank_frame_percent_to_decimal():
    spec = InterbankSpec(
        series_id="RATE_SHIBOR_CNY_3M",
        market="上海银行同业拆借市场",
        symbol="Shibor人民币",
        indicator="3月",
        currency="CNY",
    )
    raw = pd.DataFrame({
        "报告日": ["2024-01-02", "2024-01-03"],
        "利率": [2.10, 2.20],
        "涨跌": [0.0, 10.0],
    })

    df = normalize_interbank_frame(raw, spec)

    assert list(df["value"]) == [0.021, pytest.approx(0.022)]
    assert list(pd.to_datetime(df["known_at"]).dt.date) == [
        pd.Timestamp("2024-01-03").date(),
        pd.Timestamp("2024-01-04").date(),
    ]


def test_normalize_policy_rate_frame_percent_to_decimal():
    spec = PolicyRateSpec(
        series_id="RATE_POLICY_CN",
        akshare_func="macro_bank_china_interest_rate",
        currency="CNY",
        country="CN",
    )
    raw = pd.DataFrame({
        "商品": ["中国央行决议报告"],
        "日期": ["2024-02-20"],
        "今值": [3.45],
        "预测值": [None],
        "前值": [3.55],
    })

    df = normalize_policy_rate_frame(raw, spec)

    assert df["value"].iloc[0] == 0.0345
    assert pd.Timestamp(df["effective_date"].iloc[0]).date() == pd.Timestamp("2024-02-20").date()


def test_filter_dates_uses_yyyymmdd_bounds():
    df = pd.DataFrame({
        "effective_date": pd.to_datetime(["2024-01-01", "2024-02-01", "2024-03-01"]),
        "value": [1, 2, 3],
    })

    filtered = _filter_dates(df, "20240201", "20240229")

    assert list(filtered["value"]) == [2]


def test_normalize_fred_rate_frame_percent_to_decimal():
    spec = FredRateSpec(
        series_id="RATE_SOFR_USD_ON",
        fred_id="SOFR",
        currency="USD",
        description="Secured Overnight Financing Rate",
    )
    raw = pd.DataFrame({
        "observation_date": ["2024-01-02", "2024-01-03", "2024-01-04"],
        "SOFR": ["5.31", ".", "5.32"],
    })

    df = normalize_fred_rate_frame(raw, spec)

    assert list(df["value"]) == [pytest.approx(0.0531), pytest.approx(0.0532)]
    assert list(pd.to_datetime(df["known_at"]).dt.date) == [
        pd.Timestamp("2024-01-03").date(),
        pd.Timestamp("2024-01-05").date(),
    ]


def test_macro_series_catalog_contains_replacement_rates():
    records = {row["series_id"]: row for row in macro_series_catalog()}

    assert records["rate.us.sofr.on"]["fred_id"] == "SOFR"
    assert records["rate.uk.sonia.on"]["fred_id"] == "IUDSOIA"
    assert records["rate.eu.estr.on"]["fred_id"] == "ECBESTRVOLWGTTRMDMNRT"
    assert records["rate.uk.sonia.on"]["fallback_note"]

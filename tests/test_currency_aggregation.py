import pytest
from datetime import date, timedelta
from decimal import Decimal
from optifolio_contracts.quality import ValuationFreshness, ValuationQuality
from src.core.book_valuation import ValuationResult
from src.analytics.currency_aggregation import FxQuote, CurrencyAggregator, CurrencyAggregationResult


def create_val(amount, currency, quality=ValuationQuality.CONFIRMED, is_estimate=False):
    return ValuationResult(
        amount=amount,
        currency=currency,
        valuation_date=date(2026, 6, 1),
        known_at=date(2026, 6, 1),
        source_type="manual",
        source_id="test",
        quality=quality,
        freshness=ValuationFreshness.CURRENT,
        is_estimate=is_estimate,
        age_days=0
    )


def test_basic_aggregation():
    aggregator = CurrencyAggregator()
    vals = [
        create_val(100.0, "CNY"),
        create_val(200.0, "CNY"),
        create_val(100.0, "USD"),
    ]
    fx_quotes = [
        FxQuote("USD", "CNY", Decimal("7.2"), date(2026, 6, 1), "test", ValuationQuality.CONFIRMED)
    ]

    result = aggregator.aggregate(vals, fx_quotes, as_of=date(2026, 6, 1))

    assert result.reporting_currency == "CNY"
    assert result.by_original_currency["CNY"].amount_original == Decimal("300")
    assert result.by_original_currency["CNY"].amount_reporting == Decimal("300")
    assert result.by_original_currency["USD"].amount_original == Decimal("100")
    assert result.by_original_currency["USD"].amount_reporting == Decimal("720")
    assert result.reporting_total == Decimal("1020")
    assert result.reporting_total_is_exact is True


def test_inverse_fx():
    aggregator = CurrencyAggregator()
    vals = [
        create_val(100.0, "USD"),
    ]
    # 1 CNY = 0.14 USD -> 1 USD = 1/0.14 CNY
    fx_quotes = [
        FxQuote("CNY", "USD", Decimal("0.14"), date(2026, 6, 1), "test", ValuationQuality.CONFIRMED)
    ]

    result = aggregator.aggregate(vals, fx_quotes, as_of=date(2026, 6, 1))

    expected_rate = Decimal("1") / Decimal("0.14")
    assert result.by_original_currency["USD"].amount_reporting == Decimal("100") * expected_rate


def test_missing_fx():
    aggregator = CurrencyAggregator()
    vals = [
        create_val(100.0, "CNY"),
        create_val(100.0, "GBP"),
    ]
    fx_quotes = [] # No GBP/CNY

    result = aggregator.aggregate(vals, fx_quotes, as_of=date(2026, 6, 1))

    assert result.by_original_currency["CNY"].amount_reporting == Decimal("100")
    assert result.by_original_currency["GBP"].amount_reporting == Decimal("0")
    assert result.reporting_total == Decimal("100")
    assert result.reporting_total_is_exact is False
    assert result.by_original_currency["GBP"].is_estimated is True


def test_stale_fx():
    aggregator = CurrencyAggregator(stale_threshold_days=3)
    vals = [
        create_val(100.0, "USD"),
    ]
    # FX is 5 days old
    fx_quotes = [
        FxQuote("USD", "CNY", Decimal("7.2"), date(2026, 5, 27), "test", ValuationQuality.CONFIRMED)
    ]

    result = aggregator.aggregate(vals, fx_quotes, as_of=date(2026, 6, 1))

    assert result.by_original_currency["USD"].is_estimated is True
    assert result.by_original_currency["USD"].amount_reporting == Decimal("720")


def test_future_fx_rejected():
    aggregator = CurrencyAggregator()
    vals = [
        create_val(100.0, "USD"),
    ]
    # FX is from the future
    fx_quotes = [
        FxQuote("USD", "CNY", Decimal("7.2"), date(2026, 6, 2), "test", ValuationQuality.CONFIRMED)
    ]

    result = aggregator.aggregate(vals, fx_quotes, as_of=date(2026, 6, 1))

    assert result.reporting_total_is_exact is False
    assert result.by_original_currency["USD"].amount_reporting == Decimal("0")


def test_negative_amounts():
    aggregator = CurrencyAggregator()
    vals = [
        create_val(-1000.0, "USD"), # A debt
    ]
    fx_quotes = [
        FxQuote("USD", "CNY", Decimal("7.2"), date(2026, 6, 1), "test", ValuationQuality.CONFIRMED)
    ]

    result = aggregator.aggregate(vals, fx_quotes, as_of=date(2026, 6, 1))

    assert result.by_original_currency["USD"].amount_original == Decimal("-1000")
    assert result.by_original_currency["USD"].amount_reporting == Decimal("-7200")
    assert result.reporting_total == Decimal("-7200")


def test_other_rollup():
    # Only CNY and USD are major
    aggregator = CurrencyAggregator(major_currencies={"CNY", "USD"})
    vals = [
        create_val(100.0, "CNY"),
        create_val(100.0, "USD"),
        create_val(100.0, "EUR"), # Minor
        create_val(100.0, "JPY"), # Minor
    ]
    fx_quotes = [
        FxQuote("USD", "CNY", Decimal("7.2"), date(2026, 6, 1), "test", ValuationQuality.CONFIRMED),
        FxQuote("EUR", "CNY", Decimal("8.0"), date(2026, 6, 1), "test", ValuationQuality.CONFIRMED),
        FxQuote("JPY", "CNY", Decimal("0.05"), date(2026, 6, 1), "test", ValuationQuality.CONFIRMED),
    ]

    result = aggregator.aggregate(vals, fx_quotes, as_of=date(2026, 6, 1))

    assert "CNY" in result.by_original_currency
    assert "USD" in result.by_original_currency
    assert "EUR" not in result.by_original_currency
    assert "JPY" not in result.by_original_currency

    # Other roll up: EUR (800) + JPY (5) = 805
    assert result.other_currencies.amount_reporting == Decimal("805")
    assert result.other_currencies.count == 2
    assert result.reporting_total == Decimal("100") + Decimal("720") + Decimal("805")


def test_unknown_amounts():
    aggregator = CurrencyAggregator()
    vals = [
        create_val(None, "USD"), # Unknown amount
    ]
    fx_quotes = [
        FxQuote("USD", "CNY", Decimal("7.2"), date(2026, 6, 1), "test", ValuationQuality.CONFIRMED)
    ]

    result = aggregator.aggregate(vals, fx_quotes, as_of=date(2026, 6, 1))

    assert result.by_original_currency["USD"].unknown_count == 1
    assert result.by_original_currency["USD"].amount_original == Decimal("0")
    assert result.reporting_total_is_exact is False

"""Tests for canonical instrument identifier normalization."""

from __future__ import annotations

import pytest

from optifolio_contracts.identifiers import (
    AmbiguousInstrumentIdError,
    InvalidInstrumentIdError,
    normalize_instrument_id,
    parse_instrument_id,
    validate_instrument_id,
)


class TestNormalizeInstrumentId:
    def test_already_canonical(self):
        assert normalize_instrument_id("equity.us.aapl") == "equity.us.aapl"

    def test_us_equity_ticker(self):
        assert normalize_instrument_id("AAPL") == "equity.us.aapl"
        assert normalize_instrument_id("QQQ") == "equity.us.qqq"

    def test_cn_stock_prefixed(self):
        assert normalize_instrument_id("sh600519") == "equity.cn.sh.600519"
        assert normalize_instrument_id("SZ000001") == "equity.cn.sz.000001"

    def test_cn_stock_bare_with_asset_type(self):
        assert (
            normalize_instrument_id("600519", asset_type="cn_stock")
            == "equity.cn.sh.600519"
        )
        assert (
            normalize_instrument_id("000001", asset_type="cn_stock")
            == "equity.cn.sz.000001"
        )

    def test_cn_fund_bare_with_asset_type(self):
        assert (
            normalize_instrument_id("000198", asset_type="cn_fund")
            == "fund.cn.000198"
        )

    def test_bare_cn_code_without_asset_type_is_ambiguous(self):
        with pytest.raises(AmbiguousInstrumentIdError):
            normalize_instrument_id("000001")

    def test_wmp_icbc(self):
        assert (
            normalize_instrument_id("23GS8125") == "wmp.cn.icbc.23gs8125"
        )

    def test_wmp_boc(self):
        assert (
            normalize_instrument_id("AMHQLXTTUSD01B")
            == "wmp.cn.boc.amhqlxttusd01b"
        )

    def test_wmp_bosc(self):
        assert (
            normalize_instrument_id("WPXK24M1203A")
            == "wmp.cn.bosc.wpxk24m1203a"
        )

    def test_fx_pair(self):
        assert normalize_instrument_id("USDCNY") == "fx.usd_cny.spot"
        assert normalize_instrument_id("EUR/USD") == "fx.eur_usd.spot"
        assert normalize_instrument_id("GBP_USD") == "fx.gbp_usd.spot"

    def test_old_rate_series_id(self):
        assert (
            normalize_instrument_id("RATE_SHIBOR_CNY_1Y")
            == "rate.cn.shibor.1y"
        )
        assert (
            normalize_instrument_id("RATE_SOFR_USD_ON")
            == "rate.us.sofr.on"
        )

    def test_invalid_input_raises(self):
        with pytest.raises(InvalidInstrumentIdError):
            normalize_instrument_id("")
        with pytest.raises(InvalidInstrumentIdError):
            normalize_instrument_id("not_a_symbol")


class TestValidateInstrumentId:
    def test_valid_equity_us(self):
        validate_instrument_id("equity.us.aapl")

    def test_valid_equity_cn(self):
        validate_instrument_id("equity.cn.sh.600519")

    def test_valid_fund(self):
        validate_instrument_id("fund.cn.000198")

    def test_valid_fund_etf(self):
        validate_instrument_id("fund.cn.etf.sh.510300")

    def test_valid_wmp(self):
        validate_instrument_id("wmp.cn.icbc.23gs8125")

    def test_valid_fx(self):
        validate_instrument_id("fx.usd_cny.spot")

    def test_invalid_uppercase(self):
        with pytest.raises(InvalidInstrumentIdError):
            validate_instrument_id("equity.us.AAPL")

    def test_invalid_cn_equity_missing_exchange(self):
        with pytest.raises(InvalidInstrumentIdError):
            validate_instrument_id("equity.cn.600519")

    def test_parse_returns_parts(self):
        parts = parse_instrument_id("equity.cn.sh.600519")
        assert parts.asset_class == "equity"
        assert parts.market == "cn"
        assert parts.code == "600519"

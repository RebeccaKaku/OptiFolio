"""Tests for findata adapters — thin adapters with no validation, no storage, no retry."""

import pytest
import pandas as pd
import time


# ── FetchResult dataclass ────────────────────────────────────────────

class TestFetchResult:
    def test_construction_minimal(self):
        from findata.adapters import FetchResult
        r = FetchResult(symbol="AAPL", provider="test", data=None, success=True, latency_ms=1.5)
        assert r.symbol == "AAPL"
        assert r.provider == "test"
        assert r.data is None
        assert r.success is True
        assert r.latency_ms == 1.5
        assert r.errors == []
        assert r.metadata == {}

    def test_construction_with_errors_and_metadata(self):
        from findata.adapters import FetchResult
        r = FetchResult(
            symbol="AAPL", provider="test", data=pd.DataFrame({"a": [1]}),
            success=False, latency_ms=200.0,
            errors=["timeout", "no route"],
            metadata={"retries": 1},
        )
        assert len(r.errors) == 2
        assert r.metadata["retries"] == 1
        assert not r.success

    def test_default_factories_are_distinct(self):
        from findata.adapters import FetchResult
        a = FetchResult(symbol="A", provider="p", data=None, success=True, latency_ms=1.0)
        b = FetchResult(symbol="B", provider="p", data=None, success=True, latency_ms=1.0)
        a.errors.append("e1")
        assert b.errors == []


# ── UsEquityFetcher ───────────────────────────────────────────────────

class TestUsEquityFetcher:
    def test_returns_fetchresult_on_failure(self):
        from findata.adapters.us_equity import UsEquityFetcher

        fetcher = UsEquityFetcher()
        result = fetcher.fetch("INVALID_SYMBOL_XYZ", "2026-01-01", "2026-01-05")

        from findata.adapters import FetchResult
        assert isinstance(result, FetchResult)
        assert result.success is False
        assert result.data is None
        assert len(result.errors) >= 1


# ── Registry ──────────────────────────────────────────────────────────

class TestRegistry:
    def test_get_fetcher_resolves_known_types(self):
        from findata.adapters import get_fetcher, FETCHER_REGISTRY

        # All registered keys should return something (even None for crypto/hk_equity)
        for key in FETCHER_REGISTRY:
            val = get_fetcher(key)
            if key in ("crypto", "hk_equity"):
                assert val is None, f"get_fetcher({key!r}) should be None (not yet adapted)"
            else:
                assert val is not None, f"get_fetcher({key!r}) returned None"

    def test_get_fetcher_unknown_type_returns_none(self):
        from findata.adapters import get_fetcher
        assert get_fetcher("nonexistent_type_xyz") is None

    def test_registry_keys_are_expected(self):
        from findata.adapters import FETCHER_REGISTRY
        expected = {
            "us_equity", "us_etf", "cn_stock", "cn_stock_sh", "cn_stock_sz",
            "cn_fund", "cn_fund_open", "cn_fund_etf", "cn_fund_money",
            "cn_fund_qdii", "cn_money_market_fund",
            "currency", "forex",
            "bank_wmp", "bank_wm_bosc", "bank_wm_boc", "bank_wm_icbc",
            "cn_dividend", "cn_fund_fee",
            "crypto", "hk_equity",
        }
        assert set(FETCHER_REGISTRY.keys()) == expected


# ── Protocol conformance ──────────────────────────────────────────────

class TestProtocolConformance:
    def test_all_fetchers_implement_protocol(self):
        from findata.adapters import FetcherProtocol
        from findata.adapters.us_equity import UsEquityFetcher
        from findata.adapters.cn_stock import CnStockFetcher
        from findata.adapters.cn_fund import CnFundFetcherAdapter
        from findata.adapters.forex import ForexFetcher
        from findata.adapters.bank_wmp import BankWmpFetcher
        from findata.adapters.dividend import DividendFetcher
        from findata.adapters.fund_fee import FundFeeFetcher

        for cls in [UsEquityFetcher, CnStockFetcher,
                    CnFundFetcherAdapter, ForexFetcher, BankWmpFetcher,
                    DividendFetcher, FundFeeFetcher]:
            assert issubclass(cls, FetcherProtocol), f"{cls.__name__} must subclass FetcherProtocol"

    def test_all_registry_instances_match_protocol(self):
        from findata.adapters import FetcherProtocol, FETCHER_REGISTRY
        from findata.adapters.us_equity import UsEquityFetcher
        from findata.adapters.cn_stock import CnStockFetcher
        from findata.adapters.cn_fund import CnFundFetcherAdapter
        from findata.adapters.forex import ForexFetcher
        from findata.adapters.bank_wmp import BankWmpFetcher

        for key, inst in FETCHER_REGISTRY.items():
            if inst is None:
                continue  # crypto
            assert isinstance(inst, FetcherProtocol), (
                f"registry[{key!r}] is not a FetcherProtocol"
            )

        # Concrete class checks
        assert isinstance(FETCHER_REGISTRY["us_equity"], UsEquityFetcher)
        assert isinstance(FETCHER_REGISTRY["cn_stock"], CnStockFetcher)
        assert isinstance(FETCHER_REGISTRY["forex"], ForexFetcher)
        assert isinstance(FETCHER_REGISTRY["cn_fund"], CnFundFetcherAdapter)
        assert isinstance(FETCHER_REGISTRY["bank_wmp"], BankWmpFetcher)


# ── Bank WMP classification ───────────────────────────────────────────

class TestBankWmpClassification:
    def test_classify_icbc(self):
        from findata.adapters.bank_wmp import BankWmpFetcher
        assert BankWmpFetcher._classify("23GS8125") == "icbc"
        assert BankWmpFetcher._classify("23GS8123") == "icbc"

    def test_classify_boc(self):
        from findata.adapters.bank_wmp import BankWmpFetcher
        assert BankWmpFetcher._classify("AMHQLXTTUSD01B") == "boc"
        assert BankWmpFetcher._classify("GRSDR260056") == "boc"

    def test_classify_bosc(self):
        from findata.adapters.bank_wmp import BankWmpFetcher
        assert BankWmpFetcher._classify("WPXK24M1203A") == "bosc"

    def test_classify_unknown(self):
        from findata.adapters.bank_wmp import BankWmpFetcher
        assert BankWmpFetcher._classify("???") == ""
        assert BankWmpFetcher._classify("123") == ""

    def test_fetch_unknown_pattern_returns_error(self):
        from findata.adapters.bank_wmp import BankWmpFetcher
        fetcher = BankWmpFetcher()
        result = fetcher.fetch("???", "2026-01-01", "2026-01-05")
        assert result.success is False
        assert "Unknown bank WMP" in result.errors[0]


# ── Smoke: imports succeed ────────────────────────────────────────────

class TestImports:
    def test_init_imports(self):
        from findata.adapters import FetchResult, FetcherProtocol
        assert FetchResult is not None
        assert FetcherProtocol is not None

    def test_registry_imports(self):
        from findata.adapters import get_fetcher, FETCHER_REGISTRY
        assert callable(get_fetcher)
        assert isinstance(FETCHER_REGISTRY, dict)

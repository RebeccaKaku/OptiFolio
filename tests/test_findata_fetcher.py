"""Tests for FinData/fetcher_dept — thin adapters with no validation, no storage, no retry."""

import pytest
import pandas as pd
import time
import os
import sys
from unittest.mock import patch, MagicMock, AsyncMock


# ── FetchResult dataclass ────────────────────────────────────────────

class TestFetchResult:
    def test_construction_minimal(self):
        from FinData.adapters import FetchResult
        r = FetchResult(symbol="AAPL", provider="test", data=None, success=True, latency_ms=1.5)
        assert r.symbol == "AAPL"
        assert r.provider == "test"
        assert r.data is None
        assert r.success is True
        assert r.latency_ms == 1.5
        assert r.errors == []
        assert r.metadata == {}

    def test_construction_with_errors_and_metadata(self):
        from FinData.adapters import FetchResult
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
        from FinData.adapters import FetchResult
        a = FetchResult(symbol="A", provider="p", data=None, success=True, latency_ms=1.0)
        b = FetchResult(symbol="B", provider="p", data=None, success=True, latency_ms=1.0)
        a.errors.append("e1")
        assert b.errors == []


# ── UsEquityFetcher ───────────────────────────────────────────────────

class MockUSDailyDF:
    """Simulate what akshare.stock_us_daily returns."""
    def __init__(self):
        self._df = pd.DataFrame({
            "date": ["2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05"],
            "open": [185, 186, 187, 188],
            "high": [190, 191, 192, 193],
            "low": [183, 184, 185, 186],
            "close": [189, 190, 191, 192],
            "volume": [5e7, 6e7, 7e7, 8e7],
        })

    def __getitem__(self, key):
        return self._df[key]

    def __setitem__(self, key, value):
        self._df[key] = value

    def __contains__(self, key):
        return key in self._df


class TestUsEquityFetcher:
    def test_returns_fetchresult_on_success(self):
        from FinData.adapters.us_equity import UsEquityFetcher
        from FinData.adapters import FetchResult

        mock_df = pd.DataFrame({
            "date": ["2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05"],
            "open": [185, 186, 187, 188],
            "high": [190, 191, 192, 193],
            "low": [183, 184, 185, 186],
            "close": [189, 190, 191, 192],
            "volume": [5e7, 6e7, 7e7, 8e7],
        })

        class FakeAkshare:
            @staticmethod
            def stock_us_daily(symbol, adjust):
                return mock_df.copy()

        import builtins
        _orig_import = builtins.__import__

        def _mock_import(name, *args, **kwargs):
            if name == "akshare":
                return FakeAkshare()
            return _orig_import(name, *args, **kwargs)

        fetcher = UsEquityFetcher()
        with patch("builtins.__import__", side_effect=_mock_import):
            result = fetcher.fetch("AAPL", "2024-01-01", "2024-01-05")

        assert isinstance(result, FetchResult)
        assert result.symbol == "AAPL"
        assert result.provider == "akshare-sina"
        assert result.success is True
        assert result.latency_ms >= 0
        assert result.data is not None
        assert len(result.data) >= 1  # at least one row in range

    def test_returns_fetchresult_on_failure(self):
        from FinData.adapters.us_equity import UsEquityFetcher

        fetcher = UsEquityFetcher()
        result = fetcher.fetch("INVALID_SYMBOL_XYZ", "2024-01-01", "2024-01-05")

        from FinData.adapters import FetchResult
        assert isinstance(result, FetchResult)
        assert result.success is False
        assert result.data is None
        assert len(result.errors) >= 1


# ── No .empty check / no file writes ──────────────────────────────────

class TestThinAdapterConstraints:
    """Ensure adapters do NOT add validation (.empty checks) or I/O."""

    ADAPTER_FILES = [
        "FinData/adapters/cn_stock.py",
        "FinData/adapters/cn_fund.py",
        "FinData/adapters/forex.py",
        "FinData/adapters/bank_wmp.py",
    ]

    @pytest.mark.parametrize("relpath", ADAPTER_FILES)
    def test_no_empty_check_in_adapter(self, relpath):
        """Adapter source must not contain `.empty` — that is validation logic."""
        path = os.path.join(os.path.dirname(__file__), "..", relpath)
        with open(path, encoding="utf-8") as fh:
            src = fh.read()
        # strip comments so we don't flag docstrings
        lines = [line for line in src.splitlines()
                 if not line.strip().startswith("#")]
        stripped = "\n".join(lines)
        # The adapters themselves should not call .empty on the result
        assert ".empty" not in stripped, (
            f"{relpath} contains .empty check — validation belongs elsewhere"
        )

    @pytest.mark.parametrize("relpath", ADAPTER_FILES)
    def test_no_file_writes_in_adapter(self, relpath):
        """Adapter source must not write files."""
        path = os.path.join(os.path.dirname(__file__), "..", relpath)
        with open(path, encoding="utf-8") as fh:
            src = fh.read()
        lines = [line for line in src.splitlines()
                 if not line.strip().startswith("#")]
        stripped = "\n".join(lines)
        write_markers = ["open(", "to_csv", "to_parquet", "to_excel",
                         "write(", "writelines", "dump(", "json.dump"]
        for marker in write_markers:
            assert marker not in stripped, (
                f"{relpath} contains '{marker}' — file I/O belongs elsewhere"
            )


# ── Registry ──────────────────────────────────────────────────────────

class TestRegistry:
    def test_get_fetcher_resolves_known_types(self):
        from FinData.adapters import get_fetcher, FETCHER_REGISTRY

        # All registered keys should return something (even None for crypto/hk_equity)
        for key in FETCHER_REGISTRY:
            val = get_fetcher(key)
            if key in ("crypto", "hk_equity"):
                assert val is None, f"get_fetcher({key!r}) should be None (not yet adapted)"
            else:
                assert val is not None, f"get_fetcher({key!r}) returned None"

    def test_get_fetcher_unknown_type_returns_none(self):
        from FinData.adapters import get_fetcher
        assert get_fetcher("nonexistent_type_xyz") is None

    def test_registry_keys_are_expected(self):
        from FinData.adapters import FETCHER_REGISTRY
        expected = {
            "us_equity", "us_etf", "cn_stock", "cn_stock_sh", "cn_stock_sz",
            "cn_fund", "cn_fund_open", "cn_fund_etf", "cn_fund_money",
            "cn_fund_qdii", "cn_money_market_fund",
            "currency", "forex",
            "bank_wmp", "bank_wm_bosc", "bank_wm_boc", "bank_wm_icbc",
            "crypto", "hk_equity",
        }
        assert set(FETCHER_REGISTRY.keys()) == expected


# ── Protocol conformance ──────────────────────────────────────────────

class TestProtocolConformance:
    def test_all_fetchers_implement_protocol(self):
        from FinData.adapters import FetcherProtocol
        from FinData.adapters.us_equity import UsEquityFetcher
        from FinData.adapters.cn_stock import CnStockFetcherAdapter
        from FinData.adapters.cn_fund import CnFundFetcherAdapter
        from FinData.adapters.forex import ForexFetcher
        from FinData.adapters.bank_wmp import BankWmpFetcher

        for cls in [UsEquityFetcher, CnStockFetcherAdapter,
                    CnFundFetcherAdapter, ForexFetcher, BankWmpFetcher]:
            assert issubclass(cls, FetcherProtocol), f"{cls.__name__} must subclass FetcherProtocol"

    def test_all_registry_instances_match_protocol(self):
        from FinData.adapters import FetcherProtocol
        from FinData.adapters import FETCHER_REGISTRY

        for key, inst in FETCHER_REGISTRY.items():
            if inst is None:
                continue  # crypto
            assert isinstance(inst, FetcherProtocol), (
                f"registry[{key!r}] is not a FetcherProtocol"
            )


# ── Bank WMP classification ───────────────────────────────────────────

class TestBankWmpClassification:
    def test_classify_icbc(self):
        from FinData.adapters.bank_wmp import BankWmpFetcher
        assert BankWmpFetcher._classify("23GS8125") == "icbc"
        assert BankWmpFetcher._classify("23GS8123") == "icbc"

    def test_classify_boc(self):
        from FinData.adapters.bank_wmp import BankWmpFetcher
        assert BankWmpFetcher._classify("AMHQLXTTUSD01B") == "boc"
        assert BankWmpFetcher._classify("GRSDR260056") == "boc"

    def test_classify_bosc(self):
        from FinData.adapters.bank_wmp import BankWmpFetcher
        assert BankWmpFetcher._classify("WPXK24M1203A") == "bosc"

    def test_classify_unknown(self):
        from FinData.adapters.bank_wmp import BankWmpFetcher
        assert BankWmpFetcher._classify("???") == ""
        assert BankWmpFetcher._classify("123") == ""

    def test_fetch_unknown_pattern_returns_error(self):
        from FinData.adapters.bank_wmp import BankWmpFetcher
        fetcher = BankWmpFetcher()
        result = fetcher.fetch("???", "2024-01-01", "2024-01-05")
        assert result.success is False
        assert "Unknown bank WMP" in result.errors[0]


# ── Smoke: imports succeed ────────────────────────────────────────────

class TestImports:
    def test_init_imports(self):
        from FinData.adapters import FetchResult, FetcherProtocol
        assert FetchResult is not None
        assert FetcherProtocol is not None

    def test_registry_imports(self):
        from FinData.adapters import get_fetcher, FETCHER_REGISTRY
        assert callable(get_fetcher)
        assert isinstance(FETCHER_REGISTRY, dict)

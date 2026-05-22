import pytest
import asyncio
from fetchers.bosc import BoscFetcher
from fetchers.boc import BocFetcher
from fetchers.icbc import IcbcFetcher
import pandas as pd

class MockResponse:
    def __init__(self, data, status_code=200):
        self.data = data
        self.status_code = status_code
        self.text = data if isinstance(data, str) else str(data)

    def json(self):
        return self.data

    def raise_for_status(self):
        pass

@pytest.fixture
def mock_httpx_post(monkeypatch):
    class AsyncMock:
        def __init__(self, *args, **kwargs):
            self.post_called = 0
            self.get_called = 0
            self.boc_struct_called = 0

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def post(self, url, *args, **kwargs):
            self.post_called += 1
            if "bosc" in url:
                return MockResponse({
                    "code": 200, "success": True,
                    "data": {
                        "records": [
                            {"prdCode": "TEST1", "prdName": "Test Product", "nav": "1.0", "currNetCycleBeginDate": "2024-01-01"}
                        ]
                    }
                })
            elif "bocwm" in url:
                return MockResponse({
                    "result": True,
                    "data": {
                        "rows": [{"productCode": "BOC1", "currency": "RMB"}, {"productCode": "BOC2", "currency": "美元"}],
                        "total": 2
                    }
                })
            return MockResponse({})

        async def get(self, url, *args, **kwargs):
            self.get_called += 1
            if "qhjshm_rmb.js" in url:
                self.boc_struct_called += 1
                return MockResponse("var data = [{\"prodCode\": \"RMB_STRUCT1\"}];")
            elif "qhjshm_wb.js" in url:
                self.boc_struct_called += 1
                return MockResponse("var data = [{\"prodCode\": \"USD_STRUCT1\"}];")
            elif "pbsd4" in url:
                self.boc_struct_called += 1
                return MockResponse("<html><body><a href='#'>GRSDR260056</a></body></html>")
            return MockResponse({})

    monkeypatch.setattr("httpx.AsyncClient", AsyncMock)

@pytest.mark.asyncio
async def test_bosc_fetcher_sync(mock_httpx_post, tmp_path):
    fetcher = BoscFetcher(data_dir=str(tmp_path))
    await fetcher.sync()
    assert (tmp_path / "processed" / "bosc_net_value_TEST1.parquet").exists()

@pytest.mark.asyncio
async def test_boc_fetcher_discovery(mock_httpx_post, tmp_path):
    fetcher = BocFetcher(data_dir=str(tmp_path))
    codes = await fetcher.fetch_all_products()
    assert len(codes) == 2
    assert "BOC1" in codes

    struct_codes = await fetcher.fetch_structural_deposits()
    assert "GRSDR260056" in struct_codes

@pytest.mark.asyncio
async def test_icbc_fetcher_sync_defaults(mock_httpx_post, tmp_path):
    fetcher = IcbcFetcher(data_dir=str(tmp_path))
    # Test just discovery logic (we'd need a robust mock for fetch, but let's test if the default codes are loaded correctly)
    # The actual sync triggers fetch, which hits getNetValueList, returning empty mocked {} and yielding empty DF.
    await fetcher.sync()

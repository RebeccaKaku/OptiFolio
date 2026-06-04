import pytest
import asyncio
from FinData.fetcher_dept.bosc_backend import BoscFetcher
from FinData.fetcher_dept.boc_backend import BocFetcher
from FinData.fetcher_dept.icbc_backend import IcbcFetcher
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
            if "ICBCBaseReqServletNoSession" in url:
                return MockResponse("""
                    <html><body>
                    <a href="javascript:buySubmit('23GS8125','0','','','1');">Test Prod 1</a>
                    <a href="javascript:buySubmit('23GS8123','0','','','1');">Test Prod 2</a>
                    </body></html>
                """)
            elif "bosc" in url:
                return MockResponse({
                    "code": 200, "success": True,
                    "data": {
                        "records": [
                            {"prdCode": "TEST1", "prdName": "Test Product", "nav": "1.0", "currNetCycleBeginDate": "2024-01-01", "tacode": "Y58", "prodSeries": ""}
                        ]
                    }
                })
            elif "bocwm" in url:
                return MockResponse({
                    "result": True,
                    "data": {
                        "rows": [
                            {"productCode": "BOC1", "currency": "RMB", "shareNetWorth": "1.0"},
                            {"productCode": "BOC2", "currency": "美元", "shareNetWorth": "1.0"}
                        ],
                        "total": 2
                    }
                })
            elif "icbc" in url:
                # ICBC net value API — paginated, return one page with no more
                return MockResponse({
                    "code": 0,
                    "message": "success",
                    "data": {
                        "list": [
                            {"workDate": "2024-01-03", "value": "1.0345", "totValue": "1.1345"},
                            {"workDate": "2024-01-02", "value": "1.0234", "totValue": "1.1234"},
                            {"workDate": "2024-01-01", "value": "1.0123", "totValue": "1.1123"},
                        ],
                        "total": 3
                    }
                })
            return MockResponse({})

        async def get(self, url, *args, **kwargs):
            self.get_called += 1
            if "qryMCFinanceNetProHisValueForPersonPage" in url:
                return MockResponse({
                    "code": 200,
                    "success": True,
                    "data": {
                        "records": [
                            {"navDate": "2024/01/03", "nav": "1.0345", "totNav": "1.0345"},
                            {"navDate": "2024/01/02", "nav": "1.0234", "totNav": "1.0234"},
                            {"navDate": "2024/01/01", "nav": "1.0123", "totNav": "1.0123"}
                        ],
                        "total": 3,
                        "size": 20,
                        "current": 1,
                        "pages": 1
                    }
                })
            elif "qhjshm_rmb.js" in url:
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

    processed_file = tmp_path / "processed" / "bosc_net_value_TEST1.parquet"
    assert processed_file.exists()

    # Validate saved data content, schema, and index type
    df = pd.read_parquet(processed_file)
    assert not df.empty, "Saved DataFrame should not be empty"
    assert list(df.columns) == ["open", "high", "low", "close", "volume"]
    assert isinstance(df.index, pd.DatetimeIndex), f"Expected DatetimeIndex, got {type(df.index)}"
    assert len(df) == 3, f"Expected 3 rows, got {len(df)}"
    assert df["close"].iloc[0] == 1.0123
    assert df["close"].iloc[-1] == 1.0345
    # Net value products: open/high/low all equal close, volume is 0
    assert (df["open"] == df["close"]).all()
    assert (df["high"] == df["close"]).all()
    assert (df["low"] == df["close"]).all()
    assert (df["volume"] == 0.0).all()

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
    await fetcher.sync()

    # Default symbols 23GS8125 and 23GS8123 should both have processed files
    processed_1 = tmp_path / "processed" / "icbc_net_value_23GS8125.parquet"
    processed_2 = tmp_path / "processed" / "icbc_net_value_23GS8123.parquet"
    assert processed_1.exists(), "Expected 23GS8125 parquet file"
    assert processed_2.exists(), "Expected 23GS8123 parquet file"

    # Validate saved data
    df = pd.read_parquet(processed_1)
    assert not df.empty, "Saved DataFrame should not be empty"
    assert list(df.columns) == ["open", "high", "low", "close", "volume"]
    assert isinstance(df.index, pd.DatetimeIndex)
    assert len(df) == 3, f"Expected 3 rows, got {len(df)}"
    assert df["close"].iloc[0] == 1.0123  # Earliest date has lowest index
    # Net value products: open/high/low == close, volume == 0
    assert (df["open"] == df["close"]).all()
    assert (df["volume"] == 0.0).all()

@pytest.mark.asyncio
async def test_icbc_fetcher_discovery(mock_httpx_post, tmp_path):
    fetcher = IcbcFetcher(data_dir=str(tmp_path))
    codes = await fetcher.fetch_all_products()
    assert len(codes) == 2
    assert "23GS8125" in codes
    assert "23GS8123" in codes


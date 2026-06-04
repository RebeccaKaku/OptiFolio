
import pytest
from FinData.store.asset_master import AssetMasterRepository
from FinData.adapters.registry import generate_asset_id, get_namespace_prefix

def test_generate_asset_id():
    assert generate_asset_id("AAPL", "us_equity") == "US_EQ:AAPL"
    assert generate_asset_id("sh600519", "cn_stock") == "CN_STOCK:600519"
    assert generate_asset_id("600519", "cn_stock_sh") == "CN_STOCK:600519"
    assert generate_asset_id("005827", "cn_fund") == "CN_FUND:005827"
    assert generate_asset_id("BTC/USDT", "crypto") == "CRYPTO:BTC/USDT"

def test_asset_master_repository_lookup():
    # Create a temporary asset master for testing
    repo = AssetMasterRepository()
    repo.assets = {
        "US_EQ:AAPL": {
            "asset_id": "US_EQ:AAPL",
            "asset_type": "us_equity",
            "display_name": "Apple Inc.",
            "provider_symbol": "AAPL"
        },
        "CN_STOCK:600519": {
            "asset_id": "CN_STOCK:600519",
            "asset_type": "cn_stock",
            "display_name": "Kweichow Moutai",
            "provider_symbol": "sh600519"
        }
    }
    repo._legacy_symbol_map = {
        "AAPL": "US_EQ:AAPL",
        "sh600519": "CN_STOCK:600519"
    }

    # Test direct lookup
    asset = repo.get_asset("US_EQ:AAPL")
    assert asset is not None
    assert asset["display_name"] == "Apple Inc."

    # Test legacy lookup
    asset = repo.get_asset("sh600519")
    assert asset is not None
    assert asset["asset_id"] == "CN_STOCK:600519"

    # Test non-existent
    assert repo.get_asset("NON_EXISTENT") is None

def test_repository_list_and_filter():
    repo = AssetMasterRepository()
    repo.assets = {
        "US_EQ:AAPL": {"asset_id": "US_EQ:AAPL", "asset_type": "us_equity"},
        "US_EQ:MSFT": {"asset_id": "US_EQ:MSFT", "asset_type": "us_equity"},
        "CN_STOCK:600519": {"asset_id": "CN_STOCK:600519", "asset_type": "cn_stock"}
    }

    assert len(repo.list_assets()) == 3
    assert len(repo.list_assets(asset_type="us_equity")) == 2
    assert len(repo.list_assets(asset_type="cn_stock")) == 1

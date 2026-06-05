import pytest
from FinData.adapters.asset_registry import generate_asset_id
from FinData.store.asset_master import AssetMasterRepository
import os
import yaml

def test_generate_asset_id():
    assert generate_asset_id("AAPL", "us_equity") == "US_EQ:AAPL"
    assert generate_asset_id("sh600519", "cn_stock") == "CN_STOCK:600519"
    assert generate_asset_id("600519", "cn_stock_sh") == "CN_STOCK:600519"
    assert generate_asset_id("sz000001", "cn_stock") == "CN_STOCK:000001"
    assert generate_asset_id("000001", "cn_fund") == "CN_FUND:000001"
    assert generate_asset_id("ICBC001", "icbc_wm") == "ICBC_WM:ICBC001"
    assert generate_asset_id("EUR/USD", "currency") == "FX:EUR/USD"
    assert generate_asset_id("BTC/USDT", "crypto") == "CRYPTO:BTC/USDT"

def test_asset_master_repository_lookup(tmp_path):
    config_path = tmp_path / "asset_master.yaml"
    repo = AssetMasterRepository(str(config_path))

    asset_data = {
        "asset_id": "US_EQ:AAPL",
        "asset_type": "us_equity",
        "display_name": "Apple Inc.",
        "provider_symbol": "AAPL",
        "currency": "USD"
    }

    repo.upsert_asset(asset_data)
    repo.save()

    # Reload
    repo2 = AssetMasterRepository(str(config_path))

    # Direct lookup
    asset = repo2.get_asset("US_EQ:AAPL")
    assert asset is not None
    assert asset["display_name"] == "Apple Inc."
    assert asset["asset_id"] == "US_EQ:AAPL"

    # Legacy symbol lookup
    asset_legacy = repo2.get_asset("AAPL")
    assert asset_legacy is not None
    assert asset_legacy["asset_id"] == "US_EQ:AAPL"

def test_asset_master_repository_upsert_auto_id(tmp_path):
    config_path = tmp_path / "asset_master.yaml"
    repo = AssetMasterRepository(str(config_path))

    asset_data = {
        "symbol": "sh600519",
        "asset_type": "cn_stock",
        "display_name": "Kweichow Moutai"
    }

    repo.upsert_asset(asset_data)

    asset = repo.get_asset("CN_STOCK:600519")
    assert asset is not None
    assert asset["asset_id"] == "CN_STOCK:600519"
    assert asset["provider_symbol"] == "sh600519"

def test_repository_list_and_filter(tmp_path):
    config_path = tmp_path / "asset_master.yaml"
    repo = AssetMasterRepository(str(config_path))

    repo.upsert_asset({"asset_id": "US_EQ:AAPL", "asset_type": "us_equity"})
    repo.upsert_asset({"asset_id": "US_EQ:MSFT", "asset_type": "us_equity"})
    repo.upsert_asset({"asset_id": "CN_STOCK:600519", "asset_type": "cn_stock"})

    assert len(repo.list_assets()) == 3
    assert len(repo.list_assets(asset_type="us_equity")) == 2
    assert len(repo.list_assets(asset_type="cn_stock")) == 1

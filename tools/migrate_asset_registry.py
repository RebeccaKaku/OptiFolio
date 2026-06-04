import yaml
import sys
import os
from pathlib import Path

# Add project root to sys.path to allow imports from FinData
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from FinData.adapters.registry import get_namespaced_id
from FinData.store.asset_master import AssetMasterRepository

def migrate():
    registry_path = Path("config/asset_registry.yaml")
    if not registry_path.exists():
        print(f"Error: {registry_path} not found.")
        return

    with open(registry_path, 'r', encoding='utf-8') as f:
        registry_data = yaml.safe_load(f)

    if not registry_data or 'assets' not in registry_data:
        print("No assets found in asset_registry.yaml.")
        return

    master_repo = AssetMasterRepository("config/asset_master.yaml")

    count = 0
    for asset in registry_data['assets']:
        symbol = asset.get('symbol')
        asset_type = asset.get('asset_type')

        if not symbol or not asset_type:
            continue

        asset_id = get_namespaced_id(symbol, asset_type)

        # Create new asset entry
        new_asset = asset.copy()
        new_asset['asset_id'] = asset_id

        # Optional: Clean up or restructure if needed
        # For now, we keep the original fields and add asset_id

        master_repo.add_asset(new_asset)
        count += 1
        print(f"Migrated {symbol} ({asset_type}) -> {asset_id}")

    master_repo.save()
    print(f"Migration complete. Total assets migrated: {count}")

if __name__ == "__main__":
    migrate()

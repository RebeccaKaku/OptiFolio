import yaml
import sys
import os
from typing import Dict, Any
from pathlib import Path

# Add project root to sys.path to allow imports from FinData
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from FinData.adapters.asset_registry import generate_asset_id
from FinData.store.asset_master import AssetMasterRepository

def flatten_attributes(attributes: Dict[str, Any]) -> Dict[str, Any]:
    """
    Recursively flattens nested 'attributes' keys in a dictionary.
    """
    if not isinstance(attributes, dict):
        return attributes

    flat = {}
    for k, v in attributes.items():
        if k == 'attributes' and isinstance(v, dict):
            # Merge nested attributes into current level
            inner = flatten_attributes(v)
            flat.update(inner)
        elif isinstance(v, dict):
            flat[k] = flatten_attributes(v)
        else:
            flat[k] = v
    return flat

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
        name = asset.get('name')

        if not symbol or not asset_type:
            continue

        asset_id = generate_asset_id(symbol, asset_type)

        # Create new asset entry
        new_asset = asset.copy()
        new_asset['asset_id'] = asset_id

        # Map fields to new standard
        if 'name' in new_asset:
            new_asset['display_name'] = new_asset.pop('name')
        if 'symbol' in new_asset:
            new_asset['provider_symbol'] = new_asset.pop('symbol')

        # Flatten attributes if they exist
        if 'attributes' in new_asset:
            new_asset['attributes'] = flatten_attributes(new_asset['attributes'])

        master_repo.upsert_asset(new_asset)
        count += 1
        print(f"Migrated {symbol} ({asset_type}) -> {asset_id}")

    master_repo.save()
    print(f"Migration complete. Total assets migrated: {count}")

if __name__ == "__main__":
    migrate()

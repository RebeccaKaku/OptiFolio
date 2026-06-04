"""
Migration script to generate asset_master.yaml from legacy registry and candidates.
"""

import os
import yaml
from pathlib import Path
import sys

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

from FinData.adapters.registry import generate_asset_id

def migrate():
    registry_path = Path("config/asset_registry.yaml")
    candidates_path = Path("config/candidates.yaml")
    output_path = Path("config/asset_master.yaml")

    assets_map = {} # asset_id -> asset_data

    # 1. Load registry
    if registry_path.exists():
        with open(registry_path, 'r', encoding='utf-8') as f:
            reg_data = yaml.safe_load(f)
            if reg_data and 'assets' in reg_data:
                for asset in reg_data['assets']:
                    symbol = asset.get('symbol')
                    asset_type = asset.get('asset_type')
                    if symbol and asset_type:
                        asset_id = generate_asset_id(symbol, asset_type)

                        # Extract attributes
                        attrs = asset.get('attributes', {})
                        # Handle nested attributes if they exist (seen in asset_registry.yaml)
                        while 'attributes' in attrs and isinstance(attrs['attributes'], dict):
                            attrs = attrs['attributes']

                        asset_entry = {
                            'asset_id': asset_id,
                            'asset_type': asset_type,
                            'display_name': asset.get('name', symbol),
                            'base_currency': asset.get('currency', 'CNY'),
                            'country': 'CN' if 'cn_' in asset_type else 'US' if 'us_' in asset_type else 'UNKNOWN',
                            'exchange': attrs.get('exchange', 'UNKNOWN'),
                            'timezone': 'Asia/Shanghai' if 'cn_' in asset_type else 'America/New_York' if 'us_' in asset_type else 'UTC',
                            'provider': asset.get('source', 'UNKNOWN'),
                            'provider_symbol': symbol,
                            'is_active': True,
                            'start_date': None,
                            'end_date': None
                        }
                        assets_map[asset_id] = asset_entry

    # 2. Load candidates
    if candidates_path.exists():
        with open(candidates_path, 'r', encoding='utf-8') as f:
            cand_data = yaml.safe_load(f)
            if cand_data and 'candidates' in cand_data and 'assets' in cand_data['candidates']:
                for cand in cand_data['candidates']['assets']:
                    symbol = cand.get('symbol')
                    asset_type = cand.get('type')
                    if symbol and asset_type:
                        asset_id = generate_asset_id(symbol, asset_type)
                        if asset_id not in assets_map:
                            assets_map[asset_id] = {
                                'asset_id': asset_id,
                                'asset_type': asset_type,
                                'display_name': symbol,
                                'base_currency': 'USD' if 'us_' in asset_type else 'CNY',
                                'country': 'CN' if 'cn_' in asset_type else 'US' if 'us_' in asset_type else 'UNKNOWN',
                                'exchange': 'UNKNOWN',
                                'timezone': 'Asia/Shanghai' if 'cn_' in asset_type else 'America/New_York' if 'us_' in asset_type else 'UTC',
                                'provider': 'UNKNOWN',
                                'provider_symbol': symbol,
                                'is_active': True,
                                'start_date': None,
                                'end_date': None
                            }

    # 3. Save to asset_master.yaml
    output_data = {
        'version': '1.0',
        'description': 'Migrated from asset_registry.yaml and candidates.yaml',
        'assets': list(assets_map.values())
    }

    os.makedirs(output_path.parent, exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        yaml.dump(output_data, f, allow_unicode=True, sort_keys=False)

    print(f"Migration complete. {len(assets_map)} assets migrated to {output_path}")

if __name__ == "__main__":
    migrate()

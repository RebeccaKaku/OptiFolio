import yaml
import os
from typing import Dict, List, Optional, Any
from pathlib import Path
from FinData.adapters.registry import get_namespaced_id

class AssetMasterRepository:
    """
    Repository for managing asset metadata with namespaced asset_ids.
    Source of truth: config/asset_master.yaml
    """
    def __init__(self, config_path: str = "config/asset_master.yaml"):
        self.config_path = Path(config_path)
        self.assets: Dict[str, Dict[str, Any]] = {}
        self.load()

    def load(self) -> None:
        """Load assets from the YAML configuration file."""
        if self.config_path.exists():
            try:
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    data = yaml.safe_load(f)
                    if data and 'assets' in data:
                        # assets is a list in YAML, we store it as a dict keyed by asset_id
                        self.assets = {a['asset_id']: a for a in data['assets'] if 'asset_id' in a}
            except Exception as e:
                print(f"Error loading {self.config_path}: {e}")

    def save(self) -> None:
        """Save current assets to the YAML configuration file."""
        self.config_path.parent.mkdir(parents=True, exist_ok=True)

        from datetime import datetime
        data = {
            'version': '1.0',
            'last_updated': datetime.now().isoformat(),
            'assets': sorted(list(self.assets.values()), key=lambda x: x.get('asset_id', ''))
        }

        with open(self.config_path, 'w', encoding='utf-8') as f:
            yaml.dump(data, f, allow_unicode=True, sort_keys=False, default_flow_style=False)

    def get_asset(self, asset_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve an asset by its namespaced asset_id."""
        return self.assets.get(asset_id)

    def resolve_by_symbol(self, symbol: str, asset_type: str) -> Optional[Dict[str, Any]]:
        """Resolve an asset by its legacy symbol and asset type."""
        asset_id = get_namespaced_id(symbol, asset_type)
        return self.get_asset(asset_id)

    def add_asset(self, asset_data: Dict[str, Any]) -> None:
        """Add or update an asset in the repository."""
        if 'asset_id' not in asset_data:
            # Try to generate asset_id if symbol and asset_type are provided
            if 'symbol' in asset_data and 'asset_type' in asset_data:
                asset_data['asset_id'] = get_namespaced_id(asset_data['symbol'], asset_data['asset_type'])
            else:
                raise ValueError("asset_data must contain 'asset_id' or both 'symbol' and 'asset_type'")

        self.assets[asset_data['asset_id']] = asset_data

    def list_all_assets(self) -> List[Dict[str, Any]]:
        """Return a list of all assets."""
        return list(self.assets.values())

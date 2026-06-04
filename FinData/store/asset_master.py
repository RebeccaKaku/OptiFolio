"""
Asset Master Repository - Management of namespaced asset metadata.
"""

import os
from pathlib import Path
from typing import Dict, List, Optional, Any
import yaml

class AssetMasterRepository:
    """
    Repository for managing asset metadata with namespaced asset_ids.

    Supported namespaces:
    - US_EQ:{symbol}
    - CN_STOCK:{code}
    - CN_FUND:{code}
    - ICBC_WM:{code}
    - BOC_WM:{code}
    - BOSC_WM:{code}
    - CRYPTO:{pair}
    """

    def __init__(self, config_path: str = "config/asset_master.yaml"):
        self.config_path = Path(config_path)
        self.assets: Dict[str, Dict[str, Any]] = {}
        self._legacy_symbol_map: Dict[str, str] = {}
        self.load()

    def load(self):
        """Load asset master configuration from YAML."""
        if not self.config_path.exists():
            return

        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f)
                if data and 'assets' in data:
                    for asset in data['assets']:
                        asset_id = asset.get('asset_id')
                        if asset_id:
                            self.assets[asset_id] = asset
                            # Map legacy symbols for backward compatibility
                            provider_symbol = asset.get('provider_symbol')
                            if provider_symbol:
                                self._legacy_symbol_map[provider_symbol] = asset_id

                            # Also map the part after the namespace if it's unique enough?
                            # Usually provider_symbol is the legacy symbol used.
        except Exception as e:
            print(f"Error loading asset master: {e}")

    def save(self):
        """Save asset master configuration to YAML."""
        os.makedirs(self.config_path.parent, exist_ok=True)
        data = {
            'version': '1.0',
            'assets': list(self.assets.values())
        }
        with open(self.config_path, 'w', encoding='utf-8') as f:
            yaml.dump(data, f, allow_unicode=True, sort_keys=False)

    def get_asset(self, asset_id_or_symbol: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve asset metadata by asset_id or legacy symbol.
        """
        # Try direct asset_id lookup
        if asset_id_or_symbol in self.assets:
            return self.assets[asset_id_or_symbol]

        # Try legacy symbol lookup
        asset_id = self._legacy_symbol_map.get(asset_id_or_symbol)
        if asset_id:
            return self.assets[asset_id]

        return None

    def list_assets(self, asset_type: Optional[str] = None) -> List[Dict[str, Any]]:
        """List all assets, optionally filtered by type."""
        if asset_type:
            return [a for a in self.assets.values() if a.get('asset_type') == asset_type]
        return list(self.assets.values())

    def add_asset(self, asset: Dict[str, Any]):
        """Add or update an asset in the repository."""
        asset_id = asset.get('asset_id')
        if not asset_id:
            raise ValueError("asset_id is required")
        self.assets[asset_id] = asset
        provider_symbol = asset.get('provider_symbol')
        if provider_symbol:
            self._legacy_symbol_map[provider_symbol] = asset_id

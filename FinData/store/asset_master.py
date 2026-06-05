import yaml
import os
import logging
from typing import Dict, List, Optional, Any
from pathlib import Path
from FinData.adapters.asset_registry import generate_asset_id

logger = logging.getLogger(__name__)

class AssetMasterRepository:
    """
    Asset Master Repository - Management of namespaced asset metadata.
    Source of truth: config/asset_master.yaml
    """

    def __init__(self, config_path: str = "config/asset_master.yaml"):
        self.config_path = Path(config_path)
        self.assets: Dict[str, Dict[str, Any]] = {}
        self._legacy_symbol_map: Dict[str, str] = {}
        self.load()

    def load(self) -> None:
        """Load asset master configuration from YAML and build legacy symbol map."""
        if not self.config_path.exists():
            return

        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f)
                if data and 'assets' in data:
                    self.assets.clear()
                    self._legacy_symbol_map.clear()
                    for asset in data['assets']:
                        asset_id = asset.get('asset_id')
                        if asset_id:
                            self.assets[asset_id] = asset
                            # Map legacy symbols for backward compatibility
                            provider_symbol = asset.get('provider_symbol')
                            if provider_symbol:
                                self._legacy_symbol_map[provider_symbol] = asset_id
        except Exception as e:
            logger.error(f"Error loading asset master from {self.config_path}: {e}")

    def save(self) -> None:
        """Save asset master configuration to YAML."""
        self.config_path.parent.mkdir(parents=True, exist_ok=True)

        from datetime import datetime
        data = {
            'version': '1.0',
            'last_updated': datetime.now().isoformat(),
            'assets': sorted(list(self.assets.values()), key=lambda x: x.get('asset_id', ''))
        }

        with open(self.config_path, 'w', encoding='utf-8') as f:
            yaml.dump(data, f, allow_unicode=True, sort_keys=False, default_flow_style=False)

    def get_asset(self, asset_id_or_symbol: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve asset metadata by namespaced asset_id or legacy provider_symbol.
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
        """List all assets, optionally filtered by asset_type."""
        if asset_type:
            return [a for a in self.assets.values() if a.get('asset_type') == asset_type]
        return list(self.assets.values())

    def upsert_asset(self, asset_data: Dict[str, Any]) -> None:
        """Add or update an asset in the repository."""
        asset_id = asset_data.get('asset_id')
        if not asset_id:
            # Try to generate asset_id if symbol and asset_type are provided
            symbol = asset_data.get('symbol') or asset_data.get('provider_symbol')
            asset_type = asset_data.get('asset_type')
            if symbol and asset_type:
                asset_id = generate_asset_id(symbol, asset_type)
                asset_data['asset_id'] = asset_id
            else:
                raise ValueError("asset_data must contain 'asset_id' or both 'symbol' and 'asset_type'")

        # Ensure provider_symbol is set if symbol is provided
        if 'symbol' in asset_data and 'provider_symbol' not in asset_data:
            asset_data['provider_symbol'] = asset_data['symbol']

        self.assets[asset_id] = asset_data

        provider_symbol = asset_data.get('provider_symbol')
        if provider_symbol:
            self._legacy_symbol_map[provider_symbol] = asset_id

    # Alias for backward compatibility with initial implementation
    def add_asset(self, asset_data: Dict[str, Any]) -> None:
        self.upsert_asset(asset_data)

"""
增强版资产管理器 — 薄委托层。

所有数据访问委托给 FinData (fd)、PortfolioBookDatabase 和 AssetImporter。
本模块只保留 watchlist 管理和指标计算逻辑。
"""

from __future__ import annotations

import logging
from typing import Dict, List, Any, Optional

import numpy as np
import pandas as pd

_log = logging.getLogger(__name__)


class EnhancedAssetManager:
    """资产管理器 — 委托层。

    数据访问 → findata.fd / PortfolioBookDatabase / AssetImporter。
    纯逻辑 → 关注列表、指标仪表盘。
    """

    def __init__(self, registry_path: str = "config/asset_registry.yaml",
                 enable_cache: bool = True):
        self.enable_cache = enable_cache
        self._watchlists: Dict[str, Dict[str, Any]] = {}

    # ── Asset info / listing / search ──────────────────────────────────

    def get_asset_info(self, symbol: str) -> Dict[str, Any]:
        """获取资产基本信息（委托给 AssetImporter）。"""
        try:
            from src.asset_importer import AssetImporter
            imp = AssetImporter()
            asset_def = imp.registry.get_asset(symbol)
            if asset_def:
                return asset_def.to_dict()
        except Exception as e:
            _log.warning("get_asset_info failed for %s: %s", symbol, e)
        return {"symbol": symbol, "error": "not found"}

    def list_assets(self, filter_type: Optional[str] = None) -> List[Dict[str, Any]]:
        """列出已注册资产（委托给 FinData）。"""
        try:
            from findata import fd
            assets = fd.list_assets()
            result = [{"symbol": a, "type": "unknown"} for a in assets]
            if filter_type:
                result = [r for r in result if r.get("type") == filter_type]
            return result
        except Exception as e:
            _log.warning("list_assets failed: %s", e)
            return []

    def search_assets(self, query: str, limit: int = 50) -> List[Dict[str, Any]]:
        """模糊搜索资产。"""
        assets = self.list_assets()
        q = query.lower()
        return [a for a in assets if q in a.get("symbol", "").lower()][:limit]

    # ── Import ─────────────────────────────────────────────────────────

    def import_asset(self, symbol: str, asset_type: Optional[str] = None,
                     name: Optional[str] = None, currency: Optional[str] = None,
                     refresh: bool = False, **kwargs) -> Optional[Any]:
        """导入资产（委托给 AssetImporter）。"""
        try:
            from src.asset_importer import AssetImporter
            imp = AssetImporter()
            return imp.import_asset(symbol, asset_type=asset_type,
                                   name=name, currency=currency,
                                   refresh=refresh, **kwargs)
        except Exception as e:
            _log.error("import_asset failed for %s: %s", symbol, e)
            return None

    def batch_import(self, symbols: List[str],
                     asset_type: Optional[str] = None) -> Dict[str, bool]:
        """批量导入资产。"""
        results = {}
        for sym in symbols:
            results[sym] = self.import_asset(sym, asset_type=asset_type) is not None
        return results

    # ── Price fetching ─────────────────────────────────────────────────

    def update_asset_prices(self, symbols: Optional[List[str]] = None) -> Dict[str, bool]:
        """更新资产价格（委托给 FinData Orchestrator）。"""
        try:
            from findata.orchestration.orchestrator import Orchestrator
            orch = Orchestrator()
            targets = symbols or []
            if not targets:
                from findata import fd
                targets = fd.list_assets()
            tasks = orch.schedule(asset_ids=targets)
            results = orch.dispatch(tasks)
            return {aid: r is not None for aid, r in results.items()}
        except Exception as e:
            _log.warning("update_asset_prices failed: %s", e)
            return {}

    # ── Type registry ──────────────────────────────────────────────────

    def register_asset_type(self, asset_type: str,
                           fetcher_class: Any,
                           importer_class: Optional[Any] = None) -> bool:
        """注册新资产类型（委托给 FinData adapter registry）。"""
        try:
            from findata.adapters import FETCHER_REGISTRY
            FETCHER_REGISTRY[asset_type] = fetcher_class()
            _log.info("Registered asset type: %s", asset_type)
            return True
        except Exception as e:
            _log.error("Failed to register type %s: %s", asset_type, e)
            return False

    def get_supported_types(self) -> List[str]:
        """获取支持的资产类型列表。"""
        try:
            from findata.adapters import FETCHER_REGISTRY
            return [k for k, v in FETCHER_REGISTRY.items() if v is not None]
        except Exception:
            return ['cn_stock', 'cn_fund', 'us_equity', 'currency']

    def get_fetcher_for_type(self, asset_type: str) -> Optional[Any]:
        """获取资产类型对应的 Fetcher（委托给 FinData）。"""
        try:
            from findata.adapters import get_fetcher
            return get_fetcher(asset_type)
        except Exception:
            return None

    # ── Watchlist ──────────────────────────────────────────────────────

    def add_to_watchlist(self, symbol: str, user_id: str = 'default',
                         notes: str = '') -> Dict[str, Any]:
        """添加资产到关注列表。"""
        if user_id not in self._watchlists:
            self._watchlists[user_id] = {}
        self._watchlists[user_id][symbol] = {
            "added_at": pd.Timestamp.now().isoformat(),
            "notes": notes,
        }
        return {"success": True, "symbol": symbol, "user_id": user_id}

    def remove_from_watchlist(self, symbol: str, user_id: str = 'default') -> Dict[str, Any]:
        """从关注列表移除资产。"""
        if user_id in self._watchlists and symbol in self._watchlists[user_id]:
            del self._watchlists[user_id][symbol]
            return {"success": True, "symbol": symbol, "user_id": user_id}
        return {"success": False, "error": "not in watchlist"}

    def get_watchlist(self, user_id: str = 'default') -> List[Dict[str, Any]]:
        """获取关注列表。"""
        wl = self._watchlists.get(user_id, {})
        return [{"symbol": k, **v} for k, v in wl.items()]

    def get_watchlist_with_metrics(self, user_id: str = 'default') -> List[Dict[str, Any]]:
        """获取带指标的关注列表。"""
        items = self.get_watchlist(user_id)
        for item in items:
            sym = item["symbol"]
            try:
                from findata import fd
                prices = fd.prices(sym)
                if prices is not None and len(prices) > 1:
                    rets = prices.pct_change().dropna()
                    item["last_price"] = float(prices.iloc[-1])
                    item["volatility"] = float(rets.std() * np.sqrt(252))
                    item["change_1d"] = float(rets.iloc[-1]) if len(rets) > 0 else 0.0
                else:
                    item["last_price"] = None
                    item["volatility"] = None
                    item["change_1d"] = None
            except Exception:
                item["last_price"] = None
                item["volatility"] = None
                item["change_1d"] = None
        return items

    def is_in_watchlist(self, symbol: str, user_id: str = 'default') -> bool:
        """检查资产是否在关注列表中。"""
        return symbol in self._watchlists.get(user_id, {})

    # ── Price history + metrics ───────────────────────────────────────

    def get_price_history_with_analysis(self, symbol: str, days: int = 30) -> Dict[str, Any]:
        """获取价格历史和分析指标（委托给 FinData）。"""
        try:
            from findata import fd
            end = pd.Timestamp.now().strftime("%Y-%m-%d")
            start = (pd.Timestamp.now() - pd.Timedelta(days=days)).strftime("%Y-%m-%d")
            prices = fd.prices(symbol, start=start, end=end)
            if prices is None or len(prices) < 2:
                return {"symbol": symbol, "error": "insufficient data"}
            rets = prices.pct_change().dropna()
            return {
                "symbol": symbol,
                "latest_price": float(prices.iloc[-1]),
                "volatility": float(rets.std() * np.sqrt(252)),
                "max_drawdown": float((prices / prices.cummax() - 1).min()),
                "sharpe_ratio": float(rets.mean() / rets.std() * np.sqrt(252)) if rets.std() > 0 else 0.0,
                "data_points": len(prices),
            }
        except Exception as e:
            _log.warning("get_price_history for %s failed: %s", symbol, e)
            return {"symbol": symbol, "error": str(e)}

    def get_asset_metrics_dashboard(self, symbol: str) -> Dict[str, Any]:
        """获取资产指标仪表盘（委托给 FinData DataProvider）。"""
        try:
            from findata import fd
            metrics = fd.metrics(symbol, "all")
            prices = fd.prices(symbol)
            return {
                "symbol": symbol,
                "metrics": metrics,
                "data_points": len(prices) if prices is not None else 0,
            }
        except Exception as e:
            _log.warning("get_asset_metrics_dashboard for %s failed: %s", symbol, e)
            return {"symbol": symbol, "error": str(e)}

    def get_asset_overview_data(self) -> Dict[str, Any]:
        """获取资产概览数据。"""
        try:
            from findata import fd
            assets = fd.list_assets()
            return {
                "asset_count": len(assets),
                "recent_assets": [{"symbol": a} for a in assets[:20]],
                "by_type": {},
                "total_types": 0,
                "last_updated": pd.Timestamp.now().isoformat()
            }
        except Exception as e:
            _log.warning("get_asset_overview_data failed: %s", e)
            return {"asset_count": 0, "recent_assets": []}


# ── Singleton ──────────────────────────────────────────────────────────────

_enhanced_asset_manager_instance: Optional[EnhancedAssetManager] = None


def get_enhanced_asset_manager() -> EnhancedAssetManager:
    """获取全局 EnhancedAssetManager 单例。"""
    global _enhanced_asset_manager_instance
    if _enhanced_asset_manager_instance is None:
        _enhanced_asset_manager_instance = EnhancedAssetManager()
    return _enhanced_asset_manager_instance

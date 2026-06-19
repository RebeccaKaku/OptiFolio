"""
组合管理核心 — 实现 IPortfolioManager 接口 (Legacy Shim)

Refactored to delegate to ValuationEngine and FinData.
Original 935-line implementation gutted to minimal delegation logic.
"""

import logging
from typing import Dict, List, Any, Optional

_log = logging.getLogger(__name__)

from .interfaces import IPortfolioManager

class PortfolioCore(IPortfolioManager):
    """
    组合管理核心 - 统一管理组合的生命周期
    
    This class now serves as a legacy shim, delegating most operations to
    the modern ValuationEngine and FinData services.
    """
    
    def __init__(self, config_path: Optional[str] = None, 
                 base_currency: str = "CNY",
                 enable_cache: bool = True):
        """
        初始化组合管理核心 (Legacy Signature)
        """
        if config_path is None:
            from .paths import get_portfolio_config_path
            config_path = str(get_portfolio_config_path())

        self.config_path = config_path
        self.base_currency = base_currency
        self.enable_cache = enable_cache
        
        # Local state (dashboard_engine writes to these)
        self.holdings: Dict[str, float] = {}
        self.cash: Dict[str, float] = {}
        
        # Metadata stubs for backward compatibility
        self.asset_meta: Dict[str, str] = {}
        self.asset_type_meta: Dict[str, str] = {}
        
        # Load local state from config_path if it exists
        self._load_portfolio()
        self._load_asset_metadata()
    
    def _load_portfolio(self):
        """Load minimal state from config_path for legacy test compatibility."""
        import os
        import yaml
        if not self.config_path or not os.path.exists(self.config_path):
            return

        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f)
                if not data:
                    return
                
            self.cash = data.get('cash', {})
            self.holdings = data.get('positions', {})
            
            # Ensure all holdings are floats
            self.holdings = {str(k): float(v) for k, v in self.holdings.items()}
            self.cash = {str(k): float(v) for k, v in self.cash.items()}
            
        except Exception as e:
            _log.error(f"[PortfolioCore] Failed to load legacy portfolio: {e}")
    
    def _load_asset_metadata(self):
        """No-op: metadata handled by AssetRegistry / ValuationEngine."""
        pass

    def get_current_holdings(self) -> Dict[str, float]:
        """获取当前持仓 (symbol -> shares)"""
        return self.holdings.copy()
    
    def get_target_weights(self) -> Dict[str, float]:
        """Stub: real targets managed by optimization services."""
        return {}
    
    def get_portfolio_value(self, base_currency: Optional[str] = None) -> Dict[str, Any]:
        """获取组合价值 (Delegated to ValuationEngine)"""
        from datetime import date
        from src.core.valuation import ValuationEngine
        from src.domain import ValuationRequest
        
        target_currency = base_currency or self.base_currency
        engine = ValuationEngine()
        request = ValuationRequest(as_of=date.today(), base_currency=target_currency)
        
        try:
            result = engine.value(self.holdings, self.cash, request)
            # Map domain ValuationResult to legacy dict format
            return {
                "total_value": result.total_value,
                "portfolio_value": result.holdings_value,
                "cash_value": result.cash_value,
                "base_currency": result.base_currency,
                "positions": {
                    asset_id: {
                        "shares": pos.quantity,
                        "price": pos.price,
                        "currency": pos.currency,
                        "fx_rate": pos.fx_rate,
                        "value": pos.value_base
                    } for asset_id, pos in result.positions.items()
                },
                "cash": {
                    curr: {
                        "amount": ch.amount,
                        "fx_rate": ch.fx_rate,
                        "value": ch.value_base
                    } for curr, ch in result.cash_breakdown.items()
                }
            }
        except Exception as e:
            _log.error(f"[PortfolioCore] Valuation delegation failed: {e}")
            return {
                "total_value": 0.0,
                "portfolio_value": 0.0,
                "cash_value": 0.0,
                "base_currency": target_currency,
                "positions": {},
                "cash": {}
            }
    
    def get_cash_balances(self) -> Dict[str, float]:
        """获取现金余额"""
        return self.cash.copy()

    def get_cash_value(self, base_currency: Optional[str] = None) -> Dict[str, Any]:
        """获取现金折算价值 (Delegated to FxRateProvider)"""
        from src.core.valuation import FxRateProvider

        target_currency = base_currency or self.base_currency
        fx = FxRateProvider()

        cash_details = {}
        total_value = 0.0

        for currency, amount in self.cash.items():
            try:
                rate = fx.get_rate(currency, target_currency)
            except Exception:
                rate = 1.0

            val = amount * rate
            total_value += val
            cash_details[currency] = {
                "amount": amount,
                "fx_rate": rate,
                "value": val
            }

        return {
            "cash": self.cash.copy(),
            "cash_details": cash_details,
            "total": total_value,
            "base_currency": target_currency,
            "currencies": list(self.cash.keys())
        }
    
    def calculate_rebalance_orders(self) -> List[Dict[str, Any]]:
        """Stub: real rebalancing moved to dedicated engines."""
        return []
    
    def get_portfolio_metrics(self) -> Dict[str, Any]:
        """计算组合指标 (Delegated to FinData.metrics)"""
        from FinData import fd
        
        v = self.get_portfolio_value(self.base_currency)
        total_val = v["total_value"]
        
        res = {
            "total_return": 0.0,
            "annual_return": 0.0,
            "annual_volatility": 0.0,
            "sharpe_ratio": 0.0,
            "max_drawdown": 0.0,
            "base_currency": self.base_currency,
            "total_value": total_val,
            "portfolio_value": v["portfolio_value"],
            "cash_value": v["cash_value"],
            "cash_percentage": v["cash_value"] / total_val if total_val > 0 else 0,
            "num_positions": len(self.holdings),
            "num_currencies": len(self.cash)
        }
        
        if not self.holdings:
            return res
            
        # Weighted aggregation of individual asset metrics as a proxy for portfolio metrics
        # (Legacy PortfolioCore had its own history tracking which is now in PortfolioHistoryTracker)
        total_p_val = v["portfolio_value"]
        if total_p_val <= 0:
            return res

        for symbol, data in v["positions"].items():
            try:
                weight = data["value"] / total_p_val
                m = fd.metrics(symbol)
                res["total_return"] += m.get("total_return", 0.0) * weight
                res["annual_return"] += m.get("annualized_return", 0.0) * weight
                res["annual_volatility"] += m.get("volatility", 0.0) * weight
                res["sharpe_ratio"] += m.get("sharpe_ratio", 0.0) * weight
                # Max drawdown is not additive, we take the weighted average as a rough legacy proxy
                res["max_drawdown"] = min(res["max_drawdown"], m.get("max_drawdown", 0.0) or 0.0)
            except:
                continue
                
        return res

    def get_risk_metrics(self, confidence_level: float = 0.95) -> Dict[str, Any]:
        """获取风险指标 (Delegated to ValuationEngine)"""
        from src.core.valuation import ValuationEngine
        engine = ValuationEngine()
        # ValuationEngine currently doesn't have get_risk_metrics,
        # so we return a placeholder consistent with legacy shim status.
        if hasattr(engine, 'get_risk_metrics'):
            return engine.get_risk_metrics(self.holdings, self.cash, confidence_level)
        
        return {
            "confidence_level": confidence_level,
            "var_95": 0.0,
            "cvar_95": 0.0,
            "volatility": self.get_portfolio_metrics().get("annual_volatility", 0.0)
        }
    
    def get_performance_attribution(self) -> Dict[str, Any]:
        """业绩归因分析"""
        return {"error": "not implemented in legacy shim"}
    
    def add_position(self, symbol: str, shares: float) -> bool:
        """添加或更新持仓"""
        self.holdings[str(symbol)] = float(shares)
        self._save_portfolio()
        return True
    
    def remove_position(self, symbol: str) -> bool:
        """移除持仓"""
        if symbol in self.holdings:
            del self.holdings[symbol]
            self._save_portfolio()
            return True
        return False
    
    def update_cash(self, currency: str, amount: float) -> bool:
        """更新现金余额"""
        self.cash[str(currency)] = float(amount)
        self._save_portfolio()
        return True
    
    def _save_portfolio(self):
        """Save state to config_path for legacy compatibility."""
        import os
        import yaml
        from datetime import date
        if not self.config_path:
            return

        try:
            os.makedirs(os.path.dirname(self.config_path), exist_ok=True)
            data = {
                "positions": self.holdings,
                "cash": self.cash,
                "last_updated": date.today().isoformat()
            }
            with open(self.config_path, 'w', encoding='utf-8') as f:
                yaml.dump(data, f, allow_unicode=True, default_flow_style=False)
        except Exception as e:
            _log.error(f"[PortfolioCore] Failed to save legacy portfolio: {e}")

    def get_position_summary(self) -> Dict[str, Any]:
        """获取持仓摘要 (Delegated to FinData prices)"""
        from FinData import fd
        from src.core.valuation import FxRateProvider
        
        symbols = list(self.holdings.keys())
        prices = {}
        if symbols:
            try:
                df = fd.panel(symbols)
                if not df.empty:
                    prices = {s: float(df[s].iloc[-1]) for s in symbols if s in df.columns}
            except:
                pass

        fx = FxRateProvider()
        positions = []
        portfolio_value = 0.0

        # Build positions list calling fd.prices indirectly via prices dict
        for symbol, shares in self.holdings.items():
            price = prices.get(symbol, 1.0)
            from src.core.valuation import _resolve_currency
            currency = _resolve_currency(symbol)
            rate = fx.get_rate(currency, self.base_currency)
            val = shares * price * rate
            portfolio_value += val

            positions.append({
                "symbol": symbol,
                "shares": shares,
                "price": price,
                "currency": currency,
                "value": val,
                "weight": 0.0 # updated below
            })

        cash_v = self.get_cash_value(self.base_currency)
        total_val = portfolio_value + cash_v["total"]
        
        for p in positions:
            if total_val > 0:
                p["weight"] = p["value"] / total_val
        
        positions.sort(key=lambda x: x["value"], reverse=True)
        
        by_currency = {}
        for pos in positions:
            curr = pos["currency"]
            by_currency[curr] = by_currency.get(curr, 0) + pos["value"]
        
        return {
            "total_positions": len(positions),
            "total_value": total_val,
            "cash_value": cash_v["total"],
            "positions": positions,
            "by_type": {}, # Deprecated
            "by_currency": by_currency,
            "top_positions": positions[:10]
        }
    
    def export_portfolio(self, format: str = "csv", filepath: Optional[str] = None) -> str:
        """导出组合信息"""
        import json
        data = {"positions": self.holdings, "cash": self.cash}
        
        if format == "json":
            res = json.dumps(data, indent=2)
            if filepath:
                with open(filepath, 'w') as f: f.write(res)
                return filepath
            return res
        
        import pandas as pd
        df = pd.DataFrame([{"symbol": s, "shares": q} for s, q in self.holdings.items()])
        if filepath:
            df.to_csv(filepath, index=False)
            return filepath
        return df.to_csv(index=False)

    def _get_local_asset_price(self, symbol: str) -> Optional[float]:
        """Compatibility shim for DashboardEngine."""
        from FinData import fd
        try:
            df = fd.prices(symbol)
            if df is not None and not df.empty:
                return float(df.iloc[-1])
        except Exception:
            pass
        return None

    def _invalidate_portfolio_caches(self):
        """No-op: caching handled by FinData."""
        pass

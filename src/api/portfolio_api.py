"""
组合API - 为UI层提供组合相关的统一接口
"""

from typing import Dict, List, Any, Optional
from ..core.portfolio_core import PortfolioCore


class PortfolioAPI:
    """
    组合API - 包装组合管理核心的功能，提供UI友好的接口
    """
    
    def __init__(self, portfolio_core: Optional[PortfolioCore] = None):
        """
        初始化组合API
        
        Args:
            portfolio_core: 组合管理核心实例，如果为None则创建新实例
        """
        self.portfolio_core = portfolio_core or PortfolioCore()
    
    # ==================== 持仓操作API ====================
    
    def add_position(self, symbol: str, shares: float) -> Dict[str, Any]:
        """
        添加或更新持仓API
        
        Args:
            symbol: 资产代码
            shares: 股份数量
        
        Returns:
            操作结果
        """
        try:
            # 输入验证
            if not symbol or not isinstance(symbol, str):
                return self._error_response("资产代码不能为空", "VALIDATION_ERROR")
            
            symbol = symbol.strip()
            if not symbol:
                return self._error_response("资产代码不能为空", "VALIDATION_ERROR")
            
            try:
                shares_float = float(shares)
                if shares_float <= 0:
                    return self._error_response("股份数量必须大于0", "VALIDATION_ERROR")
            except (ValueError, TypeError):
                return self._error_response("股份数量必须是有效数字", "VALIDATION_ERROR")
            
            # 调用组合核心
            success = self.portfolio_core.add_position(symbol, shares_float)
            
            if success:
                return self._success_response(
                    data={
                        "symbol": symbol,
                        "shares": shares_float,
                        "added": True
                    },
                    message=f"成功添加持仓: {symbol} ({shares_float}股)"
                )
            else:
                return self._error_response(
                    f"添加持仓失败: {symbol}",
                    "ADD_POSITION_ERROR",
                    details={"symbol": symbol, "shares": shares_float}
                )
                
        except Exception as e:
            return self._error_response(
                f"添加持仓时发生错误: {str(e)}",
                "EXCEPTION",
                details={"symbol": symbol, "shares": shares}
            )
    
    def remove_position(self, symbol: str) -> Dict[str, Any]:
        """
        移除持仓API
        
        Args:
            symbol: 资产代码
        
        Returns:
            操作结果
        """
        try:
            # 输入验证
            if not symbol or not isinstance(symbol, str):
                return self._error_response("资产代码不能为空", "VALIDATION_ERROR")
            
            symbol = symbol.strip()
            
            # 检查持仓是否存在
            holdings = self.portfolio_core.get_current_holdings()
            if symbol not in holdings:
                return self._error_response(
                    f"持仓不存在: {symbol}",
                    "POSITION_NOT_FOUND",
                    details={"symbol": symbol}
                )
            
            # 调用组合核心
            success = self.portfolio_core.remove_position(symbol)
            
            if success:
                return self._success_response(
                    data={
                        "symbol": symbol,
                        "removed": True
                    },
                    message=f"成功移除持仓: {symbol}"
                )
            else:
                return self._error_response(
                    f"移除持仓失败: {symbol}",
                    "REMOVE_POSITION_ERROR",
                    details={"symbol": symbol}
                )
                
        except Exception as e:
            return self._error_response(
                f"移除持仓时发生错误: {str(e)}",
                "EXCEPTION",
                details={"symbol": symbol}
            )
    
    def update_cash(self, currency: str, amount: float) -> Dict[str, Any]:
        """
        更新现金余额API
        
        Args:
            currency: 货币代码
            amount: 金额
        
        Returns:
            操作结果
        """
        try:
            # 输入验证
            if not currency or not isinstance(currency, str):
                return self._error_response("货币代码不能为空", "VALIDATION_ERROR")
            
            currency = currency.strip().upper()
            if not currency:
                return self._error_response("货币代码不能为空", "VALIDATION_ERROR")
            
            try:
                amount_float = float(amount)
            except (ValueError, TypeError):
                return self._error_response("金额必须是有效数字", "VALIDATION_ERROR")
            
            # 调用组合核心
            success = self.portfolio_core.update_cash(currency, amount_float)
            
            if success:
                return self._success_response(
                    data={
                        "currency": currency,
                        "amount": amount_float,
                        "updated": True
                    },
                    message=f"成功更新现金: {currency} {amount_float:,.2f}"
                )
            else:
                return self._error_response(
                    f"更新现金失败: {currency}",
                    "UPDATE_CASH_ERROR",
                    details={"currency": currency, "amount": amount_float}
                )
                
        except Exception as e:
            return self._error_response(
                f"更新现金时发生错误: {str(e)}",
                "EXCEPTION",
                details={"currency": currency, "amount": amount}
            )
    
    # ==================== 组合数据API ====================
    
    def get_portfolio_value(self, base_currency: Optional[str] = None) -> Dict[str, Any]:
        """
        获取组合价值API
        
        Args:
            base_currency: 基准货币，如果为None使用默认
        
        Returns:
            组合价值信息
        """
        try:
            if base_currency is None:
                base_currency = self.portfolio_core.base_currency
            
            # 调用组合核心
            portfolio_value = self.portfolio_core.get_portfolio_value(base_currency)
            
            return self._success_response(
                data=portfolio_value,
                message=f"组合价值: {portfolio_value.get('total_value', 0):,.2f} {base_currency}"
            )
            
        except Exception as e:
            return self._error_response(
                f"获取组合价值时发生错误: {str(e)}",
                "EXCEPTION",
                details={"base_currency": base_currency}
            )
    
    def get_current_holdings(self) -> Dict[str, Any]:
        """
        获取当前持仓API
        
        Returns:
            持仓信息
        """
        try:
            holdings = self.portfolio_core.get_current_holdings()
            
            return self._success_response(
                data={
                    "holdings": holdings,
                    "count": len(holdings)
                },
                message=f"当前持仓: {len(holdings)}个资产"
            )
            
        except Exception as e:
            return self._error_response(
                f"获取当前持仓时发生错误: {str(e)}",
                "EXCEPTION"
            )
    
    def get_cash_balances(self) -> Dict[str, Any]:
        """
        获取现金余额API
        
        Returns:
            现金余额信息
        """
        try:
            cash_value = self.portfolio_core.get_cash_value(self.portfolio_core.base_currency)
            total_cash = cash_value["total"]
            base_currency = cash_value["base_currency"]
            
            return self._success_response(
                data={
                    "cash": cash_value["cash"],
                    "cash_details": cash_value["cash_details"],
                    "total": total_cash,
                    "base_currency": base_currency,
                    "currencies": cash_value["currencies"]
                },
                message=f"现金余额: {total_cash:,.2f} {base_currency} ({len(cash_value['currencies'])}种货币)"
            )
            
        except Exception as e:
            return self._error_response(
                f"获取现金余额时发生错误: {str(e)}",
                "EXCEPTION"
            )
    
    # ==================== 分析API ====================
    
    def get_portfolio_metrics(self) -> Dict[str, Any]:
        """
        获取组合指标API
        
        Returns:
            组合指标
        """
        try:
            metrics = self.portfolio_core.get_portfolio_metrics()
            
            return self._success_response(
                data=metrics,
                message="组合指标计算完成"
            )
            
        except Exception as e:
            return self._error_response(
                f"获取组合指标时发生错误: {str(e)}",
                "EXCEPTION"
            )
    
    def get_risk_metrics(self, confidence_level: float = 0.95) -> Dict[str, Any]:
        """
        获取风险指标API
        
        Args:
            confidence_level: 置信水平
        
        Returns:
            风险指标
        """
        try:
            # 输入验证
            if not 0 < confidence_level < 1:
                return self._error_response("置信水平必须在0和1之间", "VALIDATION_ERROR")
            
            risk_metrics = self.portfolio_core.get_risk_metrics(confidence_level)
            
            return self._success_response(
                data=risk_metrics,
                message=f"风险指标计算完成 (置信水平: {confidence_level:.0%})"
            )
            
        except Exception as e:
            return self._error_response(
                f"获取风险指标时发生错误: {str(e)}",
                "EXCEPTION",
                details={"confidence_level": confidence_level}
            )
    
    def calculate_rebalance_orders(self) -> Dict[str, Any]:
        """
        计算再平衡订单API
        
        Returns:
            再平衡建议
        """
        try:
            orders = self.portfolio_core.calculate_rebalance_orders()
            
            # 计算摘要
            buy_count = sum(1 for order in orders if order["action"] == "BUY")
            sell_count = sum(1 for order in orders if order["action"] == "SELL")
            total_delta = sum(order["value_delta"] for order in orders)
            
            summary = {
                "total_orders": len(orders),
                "buy_orders": buy_count,
                "sell_orders": sell_count,
                "total_adjustment": total_delta
            }
            
            return self._success_response(
                data={
                    "orders": orders,
                    "summary": summary
                },
                message=f"再平衡建议: {len(orders)}个调整 ({buy_count}买/{sell_count}卖)"
            )
            
        except Exception as e:
            return self._error_response(
                f"计算再平衡订单时发生错误: {str(e)}",
                "EXCEPTION"
            )
    
    # ==================== 便捷API ====================
    
    def get_position_summary(self) -> Dict[str, Any]:
        """
        获取持仓摘要API
        
        Returns:
            持仓摘要
        """
        try:
            summary = self.portfolio_core.get_position_summary()
            
            return self._success_response(
                data=summary,
                message=f"持仓摘要: {summary.get('total_positions', 0)}个持仓"
            )
            
        except Exception as e:
            return self._error_response(
                f"获取持仓摘要时发生错误: {str(e)}",
                "EXCEPTION"
            )
    
    def export_portfolio(self, format: str = "csv") -> Dict[str, Any]:
        """
        导出组合信息API
        
        Args:
            format: 导出格式 (csv, json)
        
        Returns:
            导出数据
        """
        try:
            # 输入验证
            valid_formats = ["csv", "json"]
            if format not in valid_formats:
                return self._error_response(
                    f"不支持的格式: {format}，支持: {', '.join(valid_formats)}",
                    "VALIDATION_ERROR"
                )
            
            # 导出数据
            export_result = self.portfolio_core.export_portfolio(format)
            
            return self._success_response(
                data={
                    "format": format,
                    "data": export_result,
                    "exported": True
                },
                message=f"组合导出完成 ({format.upper()}格式)"
            )
            
        except Exception as e:
            return self._error_response(
                f"导出组合信息时发生错误: {str(e)}",
                "EXPORT_ERROR",
                details={"format": format}
            )
    
    # ==================== 辅助方法 ====================
    
    def _success_response(self, data: Any, message: str = "操作成功") -> Dict[str, Any]:
        """
        生成成功响应
        """
        from datetime import datetime
        return {
            "success": True,
            "message": message,
            "data": data,
            "timestamp": datetime.now().isoformat()
        }
    
    def _error_response(self, error: str, error_code: str = "UNKNOWN_ERROR",
                       details: Optional[Dict] = None) -> Dict[str, Any]:
        """
        生成错误响应
        """
        from datetime import datetime
        response = {
            "success": False,
            "error": error,
            "error_code": error_code,
            "timestamp": datetime.now().isoformat()
        }
        
        if details:
            response["details"] = details
        
        return response
    
    # ==================== 组合状态API ====================
    
    def get_portfolio_status(self) -> Dict[str, Any]:
        """
        获取组合状态API（综合信息）
        
        Returns:
            组合状态
        """
        try:
            # 并行获取多个数据
            portfolio_value = self.get_portfolio_value()
            position_summary = self.get_position_summary()
            portfolio_metrics = self.get_portfolio_metrics()
            cash_balances = self.get_cash_balances()
            rebalance_orders = self.calculate_rebalance_orders()
            
            # 合并结果
            status = {
                "portfolio_value": portfolio_value.get("data") if portfolio_value["success"] else None,
                "position_summary": position_summary.get("data") if position_summary["success"] else None,
                "portfolio_metrics": portfolio_metrics.get("data") if portfolio_metrics["success"] else None,
                "cash_balances": cash_balances.get("data") if cash_balances["success"] else None,
                "rebalance_orders": rebalance_orders.get("data") if rebalance_orders["success"] else None,
                "success": all([
                    portfolio_value["success"],
                    position_summary["success"],
                    portfolio_metrics["success"],
                    cash_balances["success"],
                    rebalance_orders["success"]
                ])
            }
            
            if status["success"]:
                return self._success_response(
                    data=status,
                    message="组合状态获取完成"
                )
            else:
                return self._error_response(
                    "获取组合状态时部分数据失败",
                    "PARTIAL_FAILURE",
                    details=status
                )
            
        except Exception as e:
            return self._error_response(
                f"获取组合状态时发生错误: {str(e)}",
                "EXCEPTION"
            )

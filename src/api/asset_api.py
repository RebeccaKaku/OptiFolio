"""
资产API - 为UI层提供资产相关的统一接口
"""

from typing import Dict, List, Any, Optional, Union
import pandas as pd
from ..core.asset_manager import AssetManager


class AssetAPI:
    """
    资产API - 包装资产管理器的功能，提供UI友好的接口
    
    设计原则：
    1. 统一响应格式
    2. 错误处理标准化
    3. 数据格式转换
    4. 输入验证
    """
    
    def __init__(self, asset_manager: Optional[AssetManager] = None):
        """
        初始化资产API
        
        Args:
            asset_manager: 资产管理器实例，如果为None则创建新实例
        """
        self.asset_manager = asset_manager or AssetManager()
    
    # ==================== 资产操作API ====================
    
    def import_asset(self, symbol: str, asset_type: Optional[str] = None, 
                    refresh: bool = False) -> Dict[str, Any]:
        """
        导入资产API
        
        Args:
            symbol: 资产代码
            asset_type: 资产类型（可选，自动推断）
            refresh: 是否刷新数据
        
        Returns:
            标准化响应字典
        """
        try:
            # 输入验证
            if not symbol or not isinstance(symbol, str):
                return self._error_response("资产代码不能为空且必须是字符串", "VALIDATION_ERROR")
            
            symbol = symbol.strip()
            if not symbol:
                return self._error_response("资产代码不能为空", "VALIDATION_ERROR")
            
            # 调用资产管理器
            result = self.asset_manager.import_asset(symbol, asset_type, refresh)
            
            # 转换为标准化响应
            if result.get("success"):
                return self._success_response(
                    data=result,
                    message=result.get("message", "资产导入成功")
                )
            else:
                return self._error_response(
                    result.get("error", "导入失败"),
                    "IMPORT_ERROR",
                    details={"symbol": symbol, "asset_type": asset_type}
                )
                
        except Exception as e:
            return self._error_response(
                f"导入资产时发生错误: {str(e)}",
                "EXCEPTION",
                details={"symbol": symbol, "asset_type": asset_type}
            )
    
    def batch_import_assets(self, symbols: List[str], 
                           asset_types: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        批量导入资产API
        
        Args:
            symbols: 资产代码列表
            asset_types: 资产类型列表（可选）
        
        Returns:
            批量导入结果
        """
        try:
            # 输入验证
            if not symbols or not isinstance(symbols, list):
                return self._error_response("资产代码列表不能为空", "VALIDATION_ERROR")
            
            # 调用资产管理器
            result = self.asset_manager.batch_import(symbols, asset_types)
            
            return self._success_response(
                data=result,
                message=f"批量导入完成: {result['summary']['success']}成功, {result['summary']['failed']}失败"
            )
            
        except Exception as e:
            return self._error_response(
                f"批量导入资产时发生错误: {str(e)}",
                "EXCEPTION",
                details={"symbols_count": len(symbols) if symbols else 0}
            )
    
    def get_asset_info(self, symbol: str) -> Dict[str, Any]:
        """
        获取资产信息API
        
        Args:
            symbol: 资产代码
        
        Returns:
            资产信息
        """
        try:
            # 输入验证
            if not symbol or not isinstance(symbol, str):
                return self._error_response("资产代码不能为空且必须是字符串", "VALIDATION_ERROR")
            
            symbol = symbol.strip()
            
            # 调用资产管理器
            asset_info = self.asset_manager.get_asset_info(symbol)
            
            if not asset_info.get("exists"):
                return self._error_response(
                    f"资产 {symbol} 不存在",
                    "ASSET_NOT_FOUND",
                    details={"symbol": symbol}
                )
            
            return self._success_response(
                data=asset_info,
                message=f"成功获取资产信息: {asset_info.get('name', symbol)}"
            )
            
        except Exception as e:
            return self._error_response(
                f"获取资产信息时发生错误: {str(e)}",
                "EXCEPTION",
                details={"symbol": symbol}
            )
    
    def list_assets(self, filter_type: Optional[str] = None, 
                   page: int = 1, page_size: int = 50) -> Dict[str, Any]:
        """
        列出资产API（支持分页）
        
        Args:
            filter_type: 过滤类型
            page: 页码（从1开始）
            page_size: 每页数量
        
        Returns:
            资产列表（分页）
        """
        try:
            # 获取所有资产
            all_assets = self.asset_manager.list_assets(filter_type)
            
            # 分页处理
            total = len(all_assets)
            start_idx = (page - 1) * page_size
            end_idx = start_idx + page_size
            
            paginated_assets = all_assets[start_idx:end_idx]
            
            pagination_info = {
                "total": total,
                "page": page,
                "page_size": page_size,
                "total_pages": (total + page_size - 1) // page_size if total > 0 else 0,
                "has_next": end_idx < total,
                "has_prev": page > 1
            }
            
            return self._success_response(
                data={
                    "assets": paginated_assets,
                    "pagination": pagination_info
                },
                message=f"成功获取资产列表: 共{total}个资产"
            )
            
        except Exception as e:
            return self._error_response(
                f"获取资产列表时发生错误: {str(e)}",
                "EXCEPTION",
                details={"filter_type": filter_type}
            )
    
    def search_assets(self, query: str, limit: int = 50) -> Dict[str, Any]:
        """
        搜索资产API
        
        Args:
            query: 搜索关键词
            limit: 返回结果数量限制
        
        Returns:
            搜索结果
        """
        try:
            # 输入验证
            if not query or not isinstance(query, str):
                return self._error_response("搜索关键词不能为空", "VALIDATION_ERROR")
            
            query = query.strip()
            if not query:
                return self._success_response(data={"assets": []}, message="空搜索关键词")
            
            # 调用资产管理器
            results = self.asset_manager.search_assets(query, limit)
            
            return self._success_response(
                data={"assets": results},
                message=f"搜索完成: 找到{len(results)}个匹配的资产"
            )
            
        except Exception as e:
            return self._error_response(
                f"搜索资产时发生错误: {str(e)}",
                "EXCEPTION",
                details={"query": query}
            )
    
    def update_asset_prices(self, symbols: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        更新资产价格API
        
        Args:
            symbols: 要更新的资产代码列表，如果为None则更新所有资产
        
        Returns:
            更新结果
        """
        try:
            # 调用资产管理器
            result = self.asset_manager.update_asset_prices(symbols)
            
            return self._success_response(
                data=result,
                message=f"价格更新完成: {result['updated']}个资产已更新"
            )
            
        except Exception as e:
            return self._error_response(
                f"更新资产价格时发生错误: {str(e)}",
                "EXCEPTION",
                details={"symbols_count": len(symbols) if symbols else 0}
            )
    
    # ==================== 资产类型API ====================
    
    def get_supported_asset_types(self) -> Dict[str, Any]:
        """
        获取支持的资产类型API
        
        Returns:
            支持的资产类型列表
        """
        try:
            asset_types = self.asset_manager.get_supported_types()
            
            # 添加类型描述
            type_descriptions = {
                "cn_stock": "中国股票",
                "cn_fund": "中国基金",
                "us_equity": "美股",
                "currency": "货币",
                "bond": "债券",
                "commodity": "商品",
                "derivative": "衍生品",
                "structured": "结构化产品"
            }
            
            enriched_types = []
            for asset_type in asset_types:
                enriched_types.append({
                    "type": asset_type,
                    "description": type_descriptions.get(asset_type, asset_type),
                    "supported": True
                })
            
            return self._success_response(
                data={"asset_types": enriched_types},
                message=f"支持{len(asset_types)}种资产类型"
            )
            
        except Exception as e:
            return self._error_response(
                f"获取支持的资产类型时发生错误: {str(e)}",
                "EXCEPTION"
            )
    
    def register_asset_type(self, asset_type: str, fetcher_class: Any,
                           importer_class: Optional[Any] = None) -> Dict[str, Any]:
        """
        注册新的资产类型API
        
        Args:
            asset_type: 资产类型
            fetcher_class: Fetcher类
            importer_class: Importer类（可选）
        
        Returns:
            注册结果
        """
        try:
            # 输入验证
            if not asset_type or not isinstance(asset_type, str):
                return self._error_response("资产类型不能为空", "VALIDATION_ERROR")
            
            success = self.asset_manager.register_asset_type(
                asset_type, fetcher_class, importer_class
            )
            
            if success:
                return self._success_response(
                    data={"asset_type": asset_type, "registered": True},
                    message=f"成功注册资产类型: {asset_type}"
                )
            else:
                return self._error_response(
                    f"注册资产类型失败: {asset_type}",
                    "REGISTRATION_ERROR"
                )
                
        except Exception as e:
            return self._error_response(
                f"注册资产类型时发生错误: {str(e)}",
                "EXCEPTION",
                details={"asset_type": asset_type}
            )
    
    # ==================== 统计API ====================
    
    def get_asset_statistics(self) -> Dict[str, Any]:
        """
        获取资产统计API
        
        Returns:
            资产统计信息
        """
        try:
            stats = self.asset_manager.get_asset_count()
            
            # 添加百分比信息
            total = stats["total"]
            if total > 0:
                for key in ["by_detailed_type", "by_simplified_type"]:
                    if key in stats:
                        for type_key, count in stats[key].items():
                            stats[key][type_key] = {
                                "count": count,
                                "percentage": count / total
                            }
            
            return self._success_response(
                data=stats,
                message=f"资产统计: 共{total}个资产"
            )
            
        except Exception as e:
            return self._error_response(
                f"获取资产统计时发生错误: {str(e)}",
                "EXCEPTION"
            )
    
    def export_assets(self, format: str = "csv", 
                     filter_type: Optional[str] = None) -> Dict[str, Any]:
        """
        导出资产API
        
        Args:
            format: 导出格式 (csv, json, yaml)
            filter_type: 过滤类型
        
        Returns:
            导出数据
        """
        try:
            # 获取资产列表
            assets = self.asset_manager.list_assets(filter_type)
            
            # 导出
            export_result = self.asset_manager.export_assets(format)
            
            return self._success_response(
                data={
                    "format": format,
                    "asset_count": len(assets),
                    "filter_type": filter_type,
                    "data": export_result
                },
                message=f"成功导出{len(assets)}个资产 ({format.upper()}格式)"
            )
            
        except Exception as e:
            return self._error_response(
                f"导出资产时发生错误: {str(e)}",
                "EXPORT_ERROR",
                details={"format": format, "filter_type": filter_type}
            )
    
    # ==================== 辅助方法 ====================
    
    def _success_response(self, data: Any, message: str = "操作成功") -> Dict[str, Any]:
        """
        生成成功响应
        
        Args:
            data: 响应数据
            message: 成功消息
        
        Returns:
            标准化成功响应
        """
        return {
            "success": True,
            "message": message,
            "data": data,
            "timestamp": self._get_timestamp()
        }
    
    def _error_response(self, error: str, error_code: str = "UNKNOWN_ERROR",
                       details: Optional[Dict] = None) -> Dict[str, Any]:
        """
        生成错误响应
        
        Args:
            error: 错误描述
            error_code: 错误代码
            details: 错误详情
        
        Returns:
            标准化错误响应
        """
        response = {
            "success": False,
            "error": error,
            "error_code": error_code,
            "timestamp": self._get_timestamp()
        }
        
        if details:
            response["details"] = details
        
        return response
    
    def _get_timestamp(self) -> str:
        """获取当前时间戳"""
        from datetime import datetime
        return datetime.now().isoformat()
    
    # ==================== 便捷方法 ====================
    
    def get_asset_count_by_type(self) -> Dict[str, Any]:
        """按类型统计资产数量（简化版）"""
        stats = self.get_asset_statistics()
        
        if not stats["success"]:
            return stats
        
        simplified_stats = {
            "total": stats["data"]["total"],
            "by_type": stats["data"]["by_simplified_type"]
        }
        
        return self._success_response(
            data=simplified_stats,
            message=f"资产类型分布: 共{simplified_stats['total']}个资产"
        )
    
    def validate_asset_symbol(self, symbol: str, asset_type: Optional[str] = None) -> Dict[str, Any]:
        """
        验证资产代码API
        
        Args:
            symbol: 资产代码
            asset_type: 预期资产类型（可选）
        
        Returns:
            验证结果
        """
        try:
            # 基本验证
            if not symbol or not isinstance(symbol, str):
                return self._error_response("资产代码无效", "INVALID_SYMBOL")
            
            symbol = symbol.strip()
            if not symbol:
                return self._error_response("资产代码不能为空", "EMPTY_SYMBOL")
            
            # 获取资产信息
            asset_info = self.asset_manager.get_asset_info(symbol)
            
            if not asset_info.get("exists"):
                return self._success_response(
                    data={
                        "valid": False,
                        "symbol": symbol,
                        "exists": False,
                        "message": "资产不存在"
                    },
                    message="验证失败: 资产不存在"
                )
            
            # 检查资产类型是否匹配
            actual_type = asset_info.get("asset_type")
            type_matched = True
            
            if asset_type and actual_type:
                # 简化类型检查
                simplified_types = {
                    "cn_stock": ["cn_stock_sh", "cn_stock_sz", "cn_stock"],
                    "cn_fund": ["cn_fund_open", "cn_fund_etf", "cn_fund_qdii", "cn_fund"],
                    "us_equity": ["us_stock", "us_equity"]
                }
                
                # 检查是否在预期的简化类型中
                if asset_type in simplified_types:
                    type_matched = actual_type in simplified_types[asset_type]
                else:
                    type_matched = actual_type == asset_type
            
            return self._success_response(
                data={
                    "valid": True,
                    "symbol": symbol,
                    "exists": True,
                    "asset_type": actual_type,
                    "expected_type": asset_type,
                    "type_matched": type_matched,
                    "name": asset_info.get("name"),
                    "currency": asset_info.get("currency")
                },
                message=f"验证成功: {asset_info.get('name', symbol)}"
            )
            
        except Exception as e:
            return self._error_response(
                f"验证资产代码时发生错误: {str(e)}",
                "VALIDATION_ERROR",
                details={"symbol": symbol}
            )
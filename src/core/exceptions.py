"""
异常定义模块

定义FM系统中使用的所有自定义异常类
"""

from typing import Dict, Any, Optional


class FMError(Exception):
    """
    FM系统基础异常类
    
    Attributes:
        message: 错误信息
        error_code: 错误代码
        details: 额外详情
    """
    
    def __init__(
        self,
        message: str,
        error_code: str = "GENERAL_ERROR",
        details: Optional[Dict[str, Any]] = None
    ):
        self.message = message
        self.error_code = error_code
        self.details = details or {}
        super().__init__(self.message)
    
    def __str__(self) -> str:
        if self.details:
            return f"[{self.error_code}] {self.message} | Details: {self.details}"
        return f"[{self.error_code}] {self.message}"
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式（用于API响应）"""
        return {
            "success": False,
            "error_code": self.error_code,
            "message": self.message,
            "details": self.details
        }


class AssetNotFoundError(FMError):
    """资产未找到异常"""
    
    def __init__(self, symbol: str, asset_type: Optional[str] = None, **kwargs):
        message = f"资产未找到: {symbol}"
        if asset_type:
            message += f" (类型: {asset_type})"
        
        super().__init__(
            message=message,
            error_code="ASSET_NOT_FOUND",
            details={"symbol": symbol, "asset_type": asset_type, **kwargs}
        )


class InvalidAssetTypeError(FMError):
    """无效资产类型异常"""
    
    def __init__(self, asset_type: str, valid_types: Optional[list] = None, **kwargs):
        message = f"无效资产类型: {asset_type}"
        if valid_types:
            message += f". 有效类型: {', '.join(valid_types)}"
        
        super().__init__(
            message=message,
            error_code="INVALID_ASSET_TYPE",
            details={"asset_type": asset_type, "valid_types": valid_types, **kwargs}
        )


class DataFetchError(FMError):
    """数据获取异常"""
    
    def __init__(
        self,
        symbol: str,
        source: str,
        original_error: Optional[Exception] = None,
        **kwargs
    ):
        message = f"无法从 {source} 获取 {symbol} 的数据"
        if original_error:
            message += f": {str(original_error)}"
        
        super().__init__(
            message=message,
            error_code="DATA_FETCH_ERROR",
            details={
                "symbol": symbol,
                "source": source,
                "original_error": str(original_error) if original_error else None,
                **kwargs
            }
        )


class DataValidationError(FMError):
    """数据验证异常"""
    
    def __init__(
        self,
        message: str,
        field: Optional[str] = None,
        value: Any = None,
        **kwargs
    ):
        super().__init__(
            message=message,
            error_code="DATA_VALIDATION_ERROR",
            details={"field": field, "value": value, **kwargs}
        )


class ConfigError(FMError):
    """配置异常"""
    
    def __init__(
        self,
        message: str,
        config_file: Optional[str] = None,
        **kwargs
    ):
        super().__init__(
            message=message,
            error_code="CONFIG_ERROR",
            details={"config_file": config_file, **kwargs}
        )


class CalculationError(FMError):
    """计算异常"""
    
    def __init__(
        self,
        message: str,
        calculation_type: Optional[str] = None,
        **kwargs
    ):
        super().__init__(
            message=message,
            error_code="CALCULATION_ERROR",
            details={"calculation_type": calculation_type, **kwargs}
        )


class NetworkError(FMError):
    """网络异常"""
    
    def __init__(
        self,
        message: str,
        url: Optional[str] = None,
        status_code: Optional[int] = None,
        **kwargs
    ):
        super().__init__(
            message=message,
            error_code="NETWORK_ERROR",
            details={"url": url, "status_code": status_code, **kwargs}
        )


class CacheError(FMError):
    """缓存异常"""
    
    def __init__(self, message: str, operation: Optional[str] = None, **kwargs):
        super().__init__(
            message=message,
            error_code="CACHE_ERROR",
            details={"operation": operation, **kwargs}
        )


class OptimizationError(FMError):
    """优化计算异常"""
    
    def __init__(
        self,
        message: str,
        solver_status: Optional[str] = None,
        **kwargs
    ):
        super().__init__(
            message=message,
            error_code="OPTIMIZATION_ERROR",
            details={"solver_status": solver_status, **kwargs}
        )


# 便捷函数
def handle_exception(
    exception: Exception,
    default_message: str = "操作失败",
    logger=None
) -> FMError:
    """
    统一异常处理函数
    
    Args:
        exception: 原始异常
        default_message: 默认错误信息
        logger: 可选的日志器
        
    Returns:
        FMError实例
    """
    if isinstance(exception, FMError):
        return exception
    
    # 包装为FMError
    fm_error = FMError(
        message=f"{default_message}: {str(exception)}",
        error_code="UNEXPECTED_ERROR",
        details={"original_error_type": type(exception).__name__}
    )
    
    if logger:
        logger.error(f"Unexpected error: {exception}", exc_info=True)
    
    return fm_error


def safe_execute(func, *args, default_return=None, error_message="执行失败", **kwargs):
    """
    安全执行函数，捕获所有异常
    
    Args:
        func: 要执行的函数
        args: 位置参数
        default_return: 失败时的默认返回值
        error_message: 错误信息前缀
        kwargs: 关键字参数
        
    Returns:
        函数返回值或default_return
    """
    try:
        return func(*args, **kwargs)
    except Exception as e:
        from src.core.logger import get_logger
        logger = get_logger("FM.SafeExecute")
        logger.error(f"{error_message}: {e}")
        return default_return
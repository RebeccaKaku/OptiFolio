"""
配置管理器 - 统一管理所有配置文件路径和配置项

设计目标：
1. 消除硬编码的文件路径
2. 提供类型安全的配置访问
3. 支持环境特定的配置
4. 简化配置变更管理
"""

import os
import yaml
from typing import Dict, Any, Optional, List
from pathlib import Path
from datetime import datetime


class ConfigManager:
    """
    配置管理器 - 统一管理所有配置文件路径和配置项
    """
    
    def __init__(self, base_dir: str = None):
        """
        初始化配置管理器
        
        Args:
            base_dir: 配置文件基目录，默认为项目根目录下的config目录
        """
        if base_dir is None:
            # 自动检测项目根目录
            current_dir = Path(__file__).parent.parent.parent
            self.base_dir = str(current_dir / "config")
        else:
            self.base_dir = base_dir
        
        # 确保配置目录存在
        os.makedirs(self.base_dir, exist_ok=True)
        
        # 配置缓存
        self._config_cache: Dict[str, Any] = {}
        
        # 配置验证规则
        self._config_validators = {
            "asset_registry": self._validate_asset_registry_config,
            "portfolio": self._validate_portfolio_config,
            "candidates": self._validate_candidates_config,
            "settings": self._validate_settings_config
        }
    
    # ==================== 配置路径获取方法 ====================
    
    def get_asset_registry_path(self) -> str:
        """获取资产注册表配置文件路径"""
        return os.path.join(self.base_dir, "asset_registry.yaml")
    
    def get_portfolio_path(self) -> str:
        """获取组合配置文件路径"""
        return os.path.join(self.base_dir, "portfolio.yaml")
    
    def get_candidates_path(self) -> str:
        """获取候选资产配置文件路径"""
        return os.path.join(self.base_dir, "candidates.yaml")
    
    def get_settings_path(self) -> str:
        """获取系统设置配置文件路径"""
        return os.path.join(self.base_dir, "settings.yaml")
    
    def get_logs_dir(self) -> str:
        """获取日志目录路径"""
        logs_dir = os.path.join(Path(self.base_dir).parent, "logs")
        os.makedirs(logs_dir, exist_ok=True)
        return logs_dir
    
    def get_data_dir(self) -> str:
        """获取数据目录路径"""
        data_dir = os.path.join(Path(self.base_dir).parent, "data")
        os.makedirs(data_dir, exist_ok=True)
        return data_dir
    
    def get_cache_dir(self) -> str:
        """获取缓存目录路径"""
        cache_dir = os.path.join(Path(self.base_dir).parent, "cache")
        os.makedirs(cache_dir, exist_ok=True)
        return cache_dir
    
    def get_temp_dir(self) -> str:
        """获取临时目录路径"""
        temp_dir = os.path.join(Path(self.base_dir).parent, "temp")
        os.makedirs(temp_dir, exist_ok=True)
        return temp_dir
    
    # ==================== 配置加载方法 ====================
    
    def load_config(self, config_type: str, validate: bool = True) -> Dict[str, Any]:
        """
        加载配置文件
        
        Args:
            config_type: 配置类型 (asset_registry, portfolio, candidates, settings)
            validate: 是否验证配置
        
        Returns:
            配置字典
        """
        # 检查缓存
        cache_key = f"{config_type}_config"
        if cache_key in self._config_cache:
            return self._config_cache[cache_key].copy()
        
        # 获取配置文件路径
        config_paths = {
            "asset_registry": self.get_asset_registry_path(),
            "portfolio": self.get_portfolio_path(),
            "candidates": self.get_candidates_path(),
            "settings": self.get_settings_path()
        }
        
        if config_type not in config_paths:
            raise ValueError(f"未知的配置类型: {config_type}")
        
        config_path = config_paths[config_type]
        
        # 加载配置文件
        config_data = self._load_yaml_file(config_path)
        
        # 验证配置
        if validate and config_type in self._config_validators:
            is_valid, error_msg = self._config_validators[config_type](config_data)
            if not is_valid:
                raise ValueError(f"配置验证失败 ({config_type}): {error_msg}")
        
        # 缓存配置
        self._config_cache[cache_key] = config_data.copy()
        
        return config_data
    
    def save_config(self, config_type: str, config_data: Dict[str, Any]) -> bool:
        """
        保存配置文件
        
        Args:
            config_type: 配置类型
            config_data: 配置数据
        
        Returns:
            是否保存成功
        """
        # 验证配置
        if config_type in self._config_validators:
            is_valid, error_msg = self._config_validators[config_type](config_data)
            if not is_valid:
                raise ValueError(f"配置验证失败 ({config_type}): {error_msg}")
        
        # 获取配置文件路径
        config_paths = {
            "asset_registry": self.get_asset_registry_path(),
            "portfolio": self.get_portfolio_path(),
            "candidates": self.get_candidates_path(),
            "settings": self.get_settings_path()
        }
        
        if config_type not in config_paths:
            raise ValueError(f"未知的配置类型: {config_type}")
        
        config_path = config_paths[config_type]
        
        # 添加时间戳
        config_data_with_metadata = config_data.copy()
        config_data_with_metadata["_metadata"] = {
            "last_updated": datetime.now().isoformat(),
            "updated_by": "config_manager"
        }
        
        # 保存文件
        success = self._save_yaml_file(config_path, config_data_with_metadata)
        
        if success:
            # 更新缓存
            cache_key = f"{config_type}_config"
            self._config_cache[cache_key] = config_data.copy()
            
            # 触发配置变更事件
            self._on_config_changed(config_type)
        
        return success
    
    def reload_config(self, config_type: str) -> Dict[str, Any]:
        """
        重新加载配置文件（清除缓存后重新加载）
        
        Args:
            config_type: 配置类型
        
        Returns:
            重新加载后的配置
        """
        cache_key = f"{config_type}_config"
        if cache_key in self._config_cache:
            del self._config_cache[cache_key]
        
        return self.load_config(config_type)
    
    def get_config_value(self, config_type: str, key_path: str, default: Any = None) -> Any:
        """
        获取配置值（支持嵌套路径）
        
        Args:
            config_type: 配置类型
            key_path: 键路径，例如 "system.mode" 或 "assets[0].symbol"
            default: 默认值
        
        Returns:
            配置值
        """
        config_data = self.load_config(config_type)
        
        # 解析键路径
        keys = key_path.split(".")
        current = config_data
        
        for key in keys:
            # 检查是否是列表索引
            if "[" in key and "]" in key:
                list_key = key.split("[")[0]
                index = int(key.split("[")[1].split("]")[0])
                
                if list_key in current and isinstance(current[list_key], list):
                    if 0 <= index < len(current[list_key]):
                        current = current[list_key][index]
                    else:
                        return default
                else:
                    return default
            else:
                if isinstance(current, dict) and key in current:
                    current = current[key]
                else:
                    return default
        
        return current
    
    # ==================== 辅助方法 ====================
    
    def _load_yaml_file(self, file_path: str) -> Dict[str, Any]:
        """加载YAML文件"""
        if not os.path.exists(file_path):
            # 文件不存在时返回空字典
            return {}
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f) or {}
        except Exception as e:
            raise IOError(f"加载YAML文件失败: {file_path} - {e}")
    
    def _save_yaml_file(self, file_path: str, data: Dict[str, Any]) -> bool:
        """保存YAML文件"""
        try:
            # 确保目录存在
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            
            with open(file_path, 'w', encoding='utf-8') as f:
                yaml.dump(data, f, allow_unicode=True, default_flow_style=False)
            
            return True
        except Exception as e:
            print(f"保存YAML文件失败: {file_path} - {e}")
            return False
    
    def _validate_asset_registry_config(self, config: Dict[str, Any]) -> tuple[bool, str]:
        """验证资产注册表配置"""
        if not isinstance(config, dict):
            return False, "配置必须是字典"
        
        # 检查必需字段
        if "assets" not in config:
            return False, "缺少 'assets' 字段"
        
        if not isinstance(config["assets"], list):
            return False, "'assets' 必须是列表"
        
        # 验证每个资产
        for i, asset in enumerate(config["assets"]):
            if not isinstance(asset, dict):
                return False, f"资产 {i} 必须是字典"
            
            if "symbol" not in asset:
                return False, f"资产 {i} 缺少 'symbol' 字段"
            
            if "asset_type" not in asset:
                return False, f"资产 {i} 缺少 'asset_type' 字段"
        
        return True, ""
    
    def _validate_portfolio_config(self, config: Dict[str, Any]) -> tuple[bool, str]:
        """验证组合配置"""
        if not isinstance(config, dict):
            return False, "配置必须是字典"
        
        # 现金字段应该是字典
        if "cash" in config and not isinstance(config["cash"], dict):
            return False, "'cash' 必须是字典"
        
        # 持仓字段应该是字典
        if "positions" in config and not isinstance(config["positions"], dict):
            return False, "'positions' 必须是字典"
        
        return True, ""
    
    def _validate_candidates_config(self, config: Dict[str, Any]) -> tuple[bool, str]:
        """验证候选资产配置"""
        if not isinstance(config, dict):
            return False, "配置必须是字典"
        
        # 检查 candidates 字段
        if "candidates" not in config:
            return False, "缺少 'candidates' 字段"
        
        candidates = config["candidates"]
        if not isinstance(candidates, dict):
            return False, "'candidates' 必须是字典"
        
        # 检查 assets 字段
        if "assets" not in candidates:
            return False, "缺少 'candidates.assets' 字段"
        
        if not isinstance(candidates["assets"], list):
            return False, "'candidates.assets' 必须是列表"
        
        # 验证每个候选资产
        for i, asset in enumerate(candidates["assets"]):
            if not isinstance(asset, dict):
                return False, f"候选资产 {i} 必须是字典"
            
            if "symbol" not in asset:
                return False, f"候选资产 {i} 缺少 'symbol' 字段"
            
            if "type" not in asset:
                return False, f"候选资产 {i} 缺少 'type' 字段"
        
        return True, ""
    
    def _validate_settings_config(self, config: Dict[str, Any]) -> tuple[bool, str]:
        """验证系统设置配置"""
        if not isinstance(config, dict):
            return False, "配置必须是字典"
        
        # 检查 system 字段
        if "system" not in config:
            return False, "缺少 'system' 字段"
        
        system = config["system"]
        if not isinstance(system, dict):
            return False, "'system' 必须是字典"
        
        # 检查 mode 字段
        if "mode" not in system:
            return False, "缺少 'system.mode' 字段"
        
        valid_modes = ["live", "backtest", "paper"]
        if system["mode"] not in valid_modes:
            return False, f"'system.mode' 必须是 {valid_modes} 之一"
        
        # 检查 parameters 字段
        if "parameters" not in config:
            return False, "缺少 'parameters' 字段"
        
        parameters = config["parameters"]
        if not isinstance(parameters, dict):
            return False, "'parameters' 必须是字典"
        
        # 检查必需参数
        required_params = ["risk_free_rate", "risk_aversion", "lookback_period"]
        for param in required_params:
            if param not in parameters:
                return False, f"缺少 'parameters.{param}' 字段"
        
        return True, ""
    
    def _on_config_changed(self, config_type: str):
        """配置变更事件处理"""
        # 这里可以添加配置变更时的处理逻辑
        # 例如：清除相关缓存、发送通知等
        print(f"[ConfigManager] 配置已变更: {config_type}")
        
        # 清除相关缓存
        related_caches = {
            "asset_registry": ["asset", "asset_list", "search"],
            "portfolio": ["portfolio", "prices", "fx"],
            "candidates": ["asset"],
            "settings": ["dashboard"]
        }
        
        if config_type in related_caches:
            # 这里可以集成到缓存系统
            print(f"[ConfigManager] 相关缓存可能需要清理: {related_caches[config_type]}")
    
    # ==================== 环境相关方法 ====================
    
    def is_production(self) -> bool:
        """检查是否是生产环境"""
        try:
            settings = self.load_config("settings")
            return settings.get("system", {}).get("mode", "live") == "live"
        except:
            return True  # 默认为生产环境
    
    def is_backtest(self) -> bool:
        """检查是否是回测环境"""
        try:
            settings = self.load_config("settings")
            return settings.get("system", {}).get("mode", "live") == "backtest"
        except:
            return False
    
    def is_paper_trading(self) -> bool:
        """检查是否是模拟交易环境"""
        try:
            settings = self.load_config("settings")
            return settings.get("system", {}).get("mode", "live") == "paper"
        except:
            return False
    
    # ==================== 全局实例 ====================
    
    _global_instance: Optional['ConfigManager'] = None
    
    @classmethod
    def get_instance(cls) -> 'ConfigManager':
        """获取全局配置管理器实例（单例模式）"""
        if cls._global_instance is None:
            cls._global_instance = ConfigManager()
        return cls._global_instance
    
    @classmethod
    def set_instance(cls, instance: 'ConfigManager'):
        """设置全局配置管理器实例（用于测试等场景）"""
        cls._global_instance = instance


# 便捷函数
def get_config_manager() -> ConfigManager:
    """获取配置管理器实例"""
    return ConfigManager.get_instance()
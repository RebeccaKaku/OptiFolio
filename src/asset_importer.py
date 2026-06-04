# src/asset_importer_fixed.py
"""
资产导入模块 - 标准版本 (修复缓存导入问题)
提供统一的资产导入接口，支持股票、基金、货币等多种资产类型。
集成 FundCurrencyDetector 进行智能币种识别。
集成 自动代码标准化（自动添加交易所前缀）功能。
支持缓存优先策略：优先使用缓存数据，只在需要时拉取更新。
"""

import os
import re
from typing import Dict, List, Optional, Any
from datetime import datetime
import yaml

# --- 依赖库导入 ---
try:
    import akshare as ak
    AKSHARE_AVAILABLE = True
except ImportError:
    AKSHARE_AVAILABLE = False
    print("[Warning] akshare not available, asset import functionality will be limited")

try:
    import yfinance as yf
    YFINANCE_AVAILABLE = True
except ImportError:
    YFINANCE_AVAILABLE = False
    print("[Warning] yfinance not available, US equity import functionality will be limited")

# --- 核心模块集成：缓存系统 ---
CACHE_AVAILABLE = None  # 延迟初始化
_cache_instance = None
_CacheKeys = None

def _lazy_import_cache():
    """延迟导入缓存模块，避免循环导入"""
    global CACHE_AVAILABLE, _cache_instance, _CacheKeys
    if CACHE_AVAILABLE is None:
        try:
            from src.core.cache import get_cache, CacheKeys
            _cache_instance = get_cache()
            _CacheKeys = CacheKeys
            CACHE_AVAILABLE = True
        except ImportError as e:
            CACHE_AVAILABLE = False
            print(f"[Warning] src.core.cache not available, caching functionality will be disabled: {e}")

# --- 核心模块集成：基金币种检测器 ---
try:
    # 尝试作为包导入
    from src.fund_currency_detector import FundCurrencyDetector
    FUND_DETECTOR_AVAILABLE = True
except ImportError:
    try:
        # 尝试直接导入（兼容脚本运行模式）
        from fund_currency_detector import FundCurrencyDetector
        FUND_DETECTOR_AVAILABLE = True
    except ImportError:
        FUND_DETECTOR_AVAILABLE = False
        print("[Warning] src.fund_currency_detector not found. Currency detection will be basic.")


OFFLINE_ASSET_FALLBACKS: Dict[str, Dict[str, Any]] = {
    "cn_stock_sh:600519": {
        "name": "贵州茅台",
        "currency": "CNY",
        "exchange": "SH",
        "source": "offline_fallback",
    },
    "cn_stock_sz:000001": {
        "name": "平安银行",
        "currency": "CNY",
        "exchange": "SZ",
        "source": "offline_fallback",
    },
    "cn_fund_qdii:002892": {
        "name": "华夏移动互联混合",
        "currency": "USD",
        "source": "offline_fallback",
    },
    "cn_fund_etf:510300": {
        "name": "沪深300ETF",
        "currency": "CNY",
        "source": "offline_fallback",
    },
    "cn_fund:23713A": {
        "name": "高盛工银理财·盛景",
        "currency": "CNY",
        "source": "offline_fallback",
    },
    "cn_fund:WH2025109A": {
        "name": "慧精灵9号",
        "currency": "CNY",
        "source": "offline_fallback",
    },
}


class AssetDefinition:
    """资产定义类 - 表示一个具体的资产配置"""
    
    def __init__(self, symbol: str, asset_type: str, name: Optional[str] = None,
                 currency: Optional[str] = None, **kwargs):
        self.symbol = symbol
        self.asset_type = asset_type
        
        # 必需属性
        self.name = name or symbol
        self.currency = currency if currency else self.infer_default_currency()
        
        # 扩展属性
        self.attributes = kwargs
        
        # 元数据
        self.source = None
        self.last_updated = None
    
    def infer_default_currency(self) -> str:
        """根据资产类型推断默认基础币种（不考虑具体名称）"""
        type_currency_map = {
            # 简化类型
            'cn_stock': 'CNY',
            'cn_fund': 'CNY',
            'us_equity': 'USD',
            
            # 向后兼容类型
            'cn_stock_sh': 'CNY',
            'cn_stock_sz': 'CNY',
            'cn_fund_open': 'CNY',
            'cn_fund_etf': 'CNY',
            'cn_fund_qdii': 'CNY',
            'cn_fund_money': 'CNY',
            'cn_fund_lof': 'CNY',
            'cn_fund_index': 'CNY',
            'us_stock': 'USD',
            'hk_stock': 'HKD',
            'currency': 'USD',
        }
        return type_currency_map.get(self.asset_type, 'CNY')
    
    def update_from_api(self, data: Dict[str, Any]) -> None:
        """从API数据更新资产信息"""
        if 'name' in data and data['name']:
            self.name = data['name']
        
        if 'currency' in data and data['currency']:
            self.currency = data['currency']
        
        # 修复：避免嵌套attributes，直接存储顶层属性
        for key, value in data.items():
            if key not in ['symbol', 'asset_type', 'name', 'currency', 'source']:
                # 直接存储属性，不创建嵌套结构
                self.attributes[key] = value
        
        self.source = data.get('source', 'unknown')
        self.last_updated = datetime.now().isoformat()
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        result = {
            'symbol': self.symbol,
            'asset_type': self.asset_type,
            'name': self.name,
            'currency': self.currency or self.infer_default_currency(), # 确保不为空
            'attributes': self.attributes.copy(),
        }
        if self.source:
            result['source'] = self.source
        if self.last_updated:
            result['last_updated'] = self.last_updated
        return result
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'AssetDefinition':
        """从字典创建AssetDefinition"""
        symbol = data['symbol']
        asset_type = data['asset_type']
        name = data.get('name', symbol)
        currency = data.get('currency')

        # If data already has an explicit 'attributes' key (e.g. from to_dict),
        # use it directly to avoid double-nesting.
        if 'attributes' in data and isinstance(data['attributes'], dict):
            kwargs = data['attributes']
        else:
            kwargs = {k: v for k, v in data.items()
                     if k not in ['symbol', 'asset_type', 'name', 'currency',
                                  'source', 'last_updated', 'attributes']}

        instance = cls(symbol, asset_type, name, currency, **kwargs)
        if 'source' in data:
            instance.source = data['source']
        if 'last_updated' in data:
            instance.last_updated = data['last_updated']
        return instance


class AssetRegistry:
    """资产注册表 - 管理所有资产定义"""
    
    def __init__(self, config_path: str = "config/asset_registry.yaml"):
        self.config_path = config_path
        self.assets: Dict[str, AssetDefinition] = {}
        self.load_config()
        
        # 初始化币种检测器
        if FUND_DETECTOR_AVAILABLE:
            self.detector = FundCurrencyDetector()
        else:
            self.detector = None
    
    def load_config(self) -> None:
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    config = yaml.safe_load(f)
                if config is None:
                    # 文件存在但为空或只包含注释
                    print(f"[AssetRegistry Info] 配置文件为空，创建默认配置")
                    self._create_default_config()
                else:
                    self._load_from_config(config)
            except Exception as e:
                print(f"[AssetRegistry Error] 加载配置文件失败: {e}")
                self._create_default_config()
        else:
            self._create_default_config()
    
    def _load_from_config(self, config: Dict[str, Any]) -> None:
        if config is None or 'assets' not in config: 
            return
        self.assets.clear()
        for asset_data in config['assets']:
            try:
                asset_def = AssetDefinition.from_dict(asset_data)
                self.assets[asset_def.symbol] = asset_def
            except Exception as e:
                print(f"[AssetRegistry Warning] 加载资产失败: {asset_data.get('symbol')} - {e}")
    
    def _create_default_config(self) -> None:
        default_config = {
            'version': '2.0',
            'description': '资产注册表 (自动前缀+智能币种)',
            'assets': []
        }
        os.makedirs(os.path.dirname(self.config_path), exist_ok=True)
        with open(self.config_path, 'w', encoding='utf-8') as f:
            yaml.dump(default_config, f, allow_unicode=True, default_flow_style=False)
    
    def save_config(self) -> None:
        config = {
            'version': '2.0',
            'description': '资产注册表 (自动前缀+智能币种)',
            'last_updated': datetime.now().isoformat(),
            'assets': [asset.to_dict() for asset in sorted(self.assets.values(), key=lambda x: x.symbol)]
        }
        os.makedirs(os.path.dirname(self.config_path), exist_ok=True)
        with open(self.config_path, 'w', encoding='utf-8') as f:
            yaml.dump(config, f, allow_unicode=True, default_flow_style=False)
            
    def register_asset(self, asset_def: AssetDefinition, overwrite: bool = False) -> bool:
        if asset_def.symbol in self.assets and not overwrite:
            return False
        self.assets[asset_def.symbol] = asset_def
        return True
    
    def get_asset(self, symbol: str) -> Optional[AssetDefinition]:
        return self.assets.get(symbol)

    def remove_asset(self, symbol: str) -> bool:
        """移除资产。成功返回 True，资产不存在返回 False。"""
        if symbol in self.assets:
            del self.assets[symbol]
            return True
        return False
        
    def list_all_assets(self) -> List[AssetDefinition]:
        return list(self.assets.values())

    def detect_currency(self, name: str, default: str = 'CNY') -> str:
        """
        使用 FundCurrencyDetector 智能检测币种
        """
        if not name:
            return default
            
        if self.detector:
            # 使用专业模块进行检测
            currency, reason = self.detector.detect_currency(name)
            if currency != 'CNY':
                print(f"    [币种识别] {name} -> {currency} (依据: {reason})")
            return currency
        else:
            return default


class AssetImporter:
    """资产导入器 - 支持缓存优先策略"""
    
    def __init__(self, registry_path: str = "config/asset_registry.yaml",
                candidates_path: str = "config/candidates.yaml"):
        self.registry = AssetRegistry(registry_path)
        self.candidates_path = candidates_path
        
        # 简化后的有效资产类型
        self.valid_asset_types = [
            'cn_stock', 'cn_fund', 'us_equity', 'currency'
        ]
        
        # 向后兼容：也支持旧类型
        self.compatible_asset_types = [
            'cn_stock_sh', 'cn_stock_sz', 
            'hk_stock',
            'cn_fund_open', 'cn_fund_etf', 'cn_fund_qdii', 
            'cn_fund_money', 'cn_fund_lof', 'cn_fund_index'
        ]
        
        # 缓存配置
        self.cache_ttl = 3600  # 1小时
        self.cache_namespace = "asset_info"
        
        # 接口优先级（根据用户要求：优先使用雪球接口）
        self.interface_priority = {
            'cn_fund': ['xueqiu', 'eastmoney'],  # 优先雪球，其次东方财富
            'cn_stock': ['eastmoney', 'xueqiu'],
            'us_equity': ['yfinance']
        }
        
        # 设置模块级全局变量为实例属性
        _lazy_import_cache()  # 确保缓存模块已加载
        self.CACHE_AVAILABLE = CACHE_AVAILABLE
        self.AKSHARE_AVAILABLE = AKSHARE_AVAILABLE
        self.YFINANCE_AVAILABLE = YFINANCE_AVAILABLE
        self.FUND_DETECTOR_AVAILABLE = FUND_DETECTOR_AVAILABLE
    
    def _infer_asset_type(self, symbol: str) -> str:
        """
        根据符号推断资产类型（智能识别）
        
        Args:
            symbol: 资产符号
        
        Returns:
            资产类型：'cn_stock', 'cn_fund', 'us_equity' 或 'currency'
        """
        symbol_str = str(symbol).strip()
        symbol_upper = symbol_str.upper()
        
        # 常见货币代码集合
        currency_codes = {'USD', 'CNY', 'EUR', 'JPY', 'GBP', 'CAD', 'AUD', 'CHF', 'HKD', 'SGD'}
        
        # 首先检查是否是货币对
        # 检查是否包含斜杠或常见货币对模式
        if '/' in symbol_str:
            # 包含斜杠，如 EUR/USD
            return 'currency'
        
        # 检查是否是常见的货币对格式（6位字母，如 USDCAD）
        if len(symbol_str) == 6 and symbol_str.isalpha():
            # 检查是否是已知的货币代码组合
            if symbol_upper[:3] in currency_codes and symbol_upper[3:] in currency_codes:
                return 'currency'
        
        # 检查是否是单个货币代码（3位字母）
        if len(symbol_str) == 3 and symbol_str.isalpha():
            if symbol_upper in currency_codes:
                return 'currency'
        
        # 检查是否是美股（字母开头，不包含数字）
        if symbol_str.isalpha():
            return 'us_equity'
        
        # 检查是否是中国股票（带sh/sz前缀）
        symbol_lower = symbol_str.lower()
        if symbol_lower.startswith(('sh', 'sz')):
            return 'cn_stock'
        
        # 检查是否是纯数字（可能是中国股票或基金）
        if symbol_str.isdigit():
            # 6位数字可能是中国股票
            if len(symbol_str) == 6:
                # 进一步检查：是否在股票列表中
                try:
                    if self.AKSHARE_AVAILABLE:
                        stock_info_df = ak.stock_info_a_code_name()
                        if symbol_str in stock_info_df['code'].astype(str).values:
                            return 'cn_stock'
                except:
                    pass
            # 默认为基金
            return 'cn_fund'
        
        # 默认为基金（其他情况，如带字母的数字代码）
        return 'cn_fund'

    def _normalize_symbol(self, symbol: str, asset_type: str) -> str:
        """标准化资产代码 (根据资产类型和前缀智能处理)"""
        symbol = str(symbol).strip()
        
        # 如果资产类型是简化的cn_stock，根据前缀处理
        if asset_type == 'cn_stock':
            symbol_lower = symbol.lower()
            
            # 如果已经带前缀，保持小写格式
            if symbol_lower.startswith(('sh', 'sz')):
                return symbol_lower
                
            # 如果是纯数字，根据数字推断交易所前缀
            if symbol.isdigit() and len(symbol) == 6:
                # 简单规则：6开头为上海，0/3开头为深圳
                if symbol.startswith(('600', '601', '603', '605', '688')):
                    return f"sh{symbol}"
                elif symbol.startswith(('000', '001', '002', '003', '300')):
                    return f"sz{symbol}"
                else:
                    # 默认上海
                    return f"sh{symbol}"
            else:
                # 非纯数字，可能已经是带前缀或其他格式，原样返回
                return symbol_lower
        elif asset_type == 'us_equity':
            # 美股：保持大写（yfinance通常使用大写）
            return symbol.upper()
        else:
            # 基金等其他类型保持原样
            return symbol

    def _get_cached_asset_info(self, symbol: str, asset_type: str) -> Optional[Dict[str, Any]]:
        """从缓存获取资产信息"""
        if not self.CACHE_AVAILABLE:
            return None
        
        try:
            # 确保缓存模块已加载
            _lazy_import_cache()
            if _cache_instance is None:
                return None
                
            cache_key = _CacheKeys.asset_info(f"{asset_type}:{symbol}")
            cached_data = _cache_instance.get(cache_key, namespace=self.cache_namespace)
            
            if cached_data:
                print(f"[Cache] 命中缓存: {symbol} ({asset_type})")
                return cached_data
        except Exception as e:
            print(f"[Cache Warning] 获取缓存失败: {e}")
        
        return None

    def _set_cached_asset_info(self, symbol: str, asset_type: str, data: Dict[str, Any]) -> bool:
        """将资产信息存入缓存"""
        if not self.CACHE_AVAILABLE:
            return False
        
        try:
            # 确保缓存模块已加载
            _lazy_import_cache()
            if _cache_instance is None:
                return False
                
            cache_key = _CacheKeys.asset_info(f"{asset_type}:{symbol}")
            success = _cache_instance.set(cache_key, data, ttl=self.cache_ttl, namespace=self.cache_namespace)
            
            if success:
                print(f"[Cache] 缓存已保存: {symbol} ({asset_type})")
            
            return success
        except Exception as e:
            print(f"[Cache Warning] 保存缓存失败: {e}")
            return False

    def import_asset(self, symbol: str, asset_type: Optional[str] = None, 
                    name: Optional[str] = None, currency: Optional[str] = None,
                    refresh: bool = False, **kwargs) -> Optional[AssetDefinition]:
        
        # 如果未提供资产类型，则智能推断
        if asset_type is None:
            asset_type = self._infer_asset_type(symbol)
            print(f"[AssetImporter] 推断资产类型: {symbol} -> {asset_type}")
        
        # 检查资产类型是否有效（支持简化类型和兼容类型）
        if asset_type not in self.valid_asset_types and asset_type not in self.compatible_asset_types:
            print(f"[Error] 无效资产类型: {asset_type}")
            return None
        
        # 1. 代码标准化
        normalized_symbol = self._normalize_symbol(symbol, asset_type)
        if normalized_symbol != symbol:
            print(f"[AssetImporter] 代码标准化: {symbol} -> {normalized_symbol}")
        
        print(f"[AssetImporter] 正在导入: {normalized_symbol} ({asset_type})")
        
        # 2. 检查缓存（除非强制刷新）
        api_data = None
        if not refresh:
            api_data = self._get_cached_asset_info(normalized_symbol, asset_type)
        
        # 3. 创建对象
        asset_def = AssetDefinition(normalized_symbol, asset_type, name, currency, **kwargs)
        
        # 4. 尝试从API获取/更新信息
        # 当未手动提供名称时，需要从API获取
        needs_api_fetch = name is None
        if refresh or (not api_data and needs_api_fetch):
            print(f"[API] 从API获取信息: {normalized_symbol}")
            api_data = self._fetch_asset_info_with_priority(normalized_symbol, asset_type)
            if not api_data:
                api_data = self._get_offline_fallback(normalized_symbol, asset_type)
            
            # 如果成功获取到API数据，存入缓存
            if api_data:
                self._set_cached_asset_info(normalized_symbol, asset_type, api_data)
        
        # 5. 使用API数据更新资产信息（但保留手动提供的 name / currency）
        manual_name = name
        manual_currency = currency
        if api_data:
            asset_def.update_from_api(api_data)
        if manual_name:
            asset_def.name = manual_name
        if manual_currency:
            asset_def.currency = manual_currency

        # 6. 智能币种补全（仅在未手动指定币种时）
        # 如果API没返回币种，或者当前是默认CNY，尝试用名称再检测一次（防止API漏掉QDII信息）
        if manual_currency:
            pass  # 手动指定的币种优先，不做自动补全
        elif (not asset_def.currency or asset_def.currency == 'CNY') and asset_def.name:
            detected = self.registry.detect_currency(asset_def.name)
            if detected != 'CNY':
                asset_def.currency = detected
        
        # 兜底：如果还是没有币种，使用类型默认值
        if not asset_def.currency:
            asset_def.currency = asset_def.infer_default_currency()
        
        # 7. 注册并保存到配置文件
        if self.registry.register_asset(asset_def, overwrite=True):
            self.registry.save_config()
            print(f"[Success] 资产导入完成: {asset_def.name} [{asset_def.currency}]")
            return asset_def
        else:
            print(f"[Error] 注册失败")
            return None

    def _get_offline_fallback(self, symbol: str, asset_type: str) -> Optional[Dict[str, Any]]:
        """Return stable metadata for core demo assets when public APIs are unavailable."""
        key = f"{asset_type}:{symbol}"
        fallback = OFFLINE_ASSET_FALLBACKS.get(key)
        if fallback:
            print(f"[Offline] 使用内置资产元数据: {symbol}")
            return fallback.copy()
        return None
    
    def _fetch_asset_info_with_priority(self, symbol: str, asset_type: str) -> Optional[Dict[str, Any]]:
        """根据接口优先级获取资产信息"""
        # 1. 尝试从本地银行理财快照中查找
        # A. 工商银行 (ICBC)
        from pathlib import Path
        import json
        icbc_meta_path = Path("FinData/data/icbc/product_metadata.json")
        icbc_found = False
        if icbc_meta_path.exists():
            try:
                with open(icbc_meta_path, "r", encoding="utf-8") as f:
                    icbc_meta = json.load(f)
                if not hasattr(self, "_icbc_meta_index"):
                    self._icbc_meta_index = {
                        p["product_code"]: p
                        for p in icbc_meta.get("products", [])
                        if p.get("product_code")
                    }
                product = self._icbc_meta_index.get(symbol)
                if product:
                    print(f"[Offline] 在工行理财元数据中找到资产: {symbol}")
                    icbc_found = True
                    return {
                        "name":                 product.get("product_name"),
                        "currency":             product.get("currency", "CNY"),
                        "establishment_date":   product.get("establishment_date"),
                        "maturity_date":        product.get("maturity_date"),
                        "subscription_period":  product.get("subscription_period"),
                        "next_open_date":       product.get("next_open_date"),
                        "min_purchase_amount":  product.get("min_purchase_amount"),
                        "term":                 product.get("term"),
                        "risk_level":           product.get("risk_level"),
                        "currency_source":      product.get("currency_source"),
                        "source":               "icbc_product_metadata",
                    }
            except Exception as e:
                print(f"[Warning] 读取工行理财元数据失败: {e}")

        # 工商银行旧版回退 (config/icbc_currencies.json)
        if not icbc_found:
            icbc_json_path = Path("config/icbc_currencies.json")
            if icbc_json_path.exists():
                try:
                    with open(icbc_json_path, "r", encoding="utf-8") as f:
                        icbc_data = json.load(f)
                        if symbol in icbc_data:
                            item = icbc_data[symbol]
                            raw_currency = item.get("currency", "元")
                            currency_map = {"元": "CNY", "人民币": "CNY", "美元": "USD", "港币": "HKD", "港元": "HKD", "欧元": "EUR"}
                            print(f"[Offline] 在工行本地映射中找到资产: {symbol}")
                            return {
                                "name": item.get("name"),
                                "currency": currency_map.get(raw_currency, "CNY"),
                                "source": "icbc_currencies_snapshot"
                            }
                except Exception as e:
                    print(f"[Warning] 读取工行本地映射失败: {e}")

        # B. 上海银行 (BOSC)
        bosc_meta_path = Path("FinData/data/bosc/product_metadata.json")
        bosc_found = False
        if bosc_meta_path.exists():
            try:
                with open(bosc_meta_path, "r", encoding="utf-8") as f:
                    bosc_meta = json.load(f)
                if not hasattr(self, "_bosc_meta_index"):
                    self._bosc_meta_index = {
                        p["product_code"]: p
                        for p in bosc_meta.get("products", [])
                        if p.get("product_code")
                    }
                product = self._bosc_meta_index.get(symbol)
                if product:
                    print(f"[Offline] 在上行理财元数据中找到资产: {symbol}")
                    bosc_found = True
                    return {
                        "name":                 product.get("product_name"),
                        "currency":             product.get("currency", "CNY"),
                        "establishment_date":   product.get("establishment_date"),
                        "maturity_date":        product.get("maturity_date"),
                        "subscription_period":  product.get("subscription_period"),
                        "next_open_date":       product.get("next_open_date"),
                        "min_purchase_amount":  product.get("min_purchase_amount"),
                        "term":                 product.get("term"),
                        "risk_level":           product.get("risk_level"),
                        "currency_source":      product.get("currency_source"),
                        "source":               "bosc_product_metadata",
                    }
            except Exception as e:
                print(f"[Warning] 读取上行理财元数据失败: {e}")

        # 上海银行旧版回退 (raw snapshot)
        if not bosc_found:
            bosc_raw_dir = Path("FinData/data/bosc/raw")
            if bosc_raw_dir.exists():
                snapshot_files = sorted(bosc_raw_dir.glob("bosc_all_products_snapshot_*.json"))
                if snapshot_files:
                    try:
                        with open(snapshot_files[-1], "r", encoding="utf-8") as f:
                            bosc_data = json.load(f)
                            records = bosc_data.get("data", {}).get("records", [])
                            for r in records:
                                if r.get("prdCode") == symbol:
                                    print(f"[Offline] 在上行本地快照中找到资产: {symbol}")
                                    return {
                                        "name": r.get("prdName"),
                                        "currency": r.get("currType", "CNY"),
                                        "source": "bosc_products_snapshot"
                                    }
                    except Exception as e:
                        print(f"[Warning] 读取上行本地快照失败: {e}")

        # C. 中银理财（BOCWM）— boc_product_metadata.json
        boc_meta_path = Path("FinData/data/boc/product_metadata.json")
        if boc_meta_path.exists():
            try:
                with open(boc_meta_path, "r", encoding="utf-8") as f:
                    boc_meta = json.load(f)
                # Build a lookup dict on first use (cached via module-level variable)
                if not hasattr(self, "_boc_meta_index"):
                    self._boc_meta_index = {
                        p["product_code"]: p
                        for p in boc_meta.get("products", [])
                        if p.get("product_code")
                    }
                product = self._boc_meta_index.get(symbol)
                if product:
                    print(f"[Offline] 在中银理财元数据中找到资产: {symbol}")
                    return {
                        "name":                 product.get("product_name"),
                        "currency":             product.get("currency", "CNY"),
                        "establishment_date":   product.get("establishment_date"),
                        "maturity_date":        product.get("maturity_date"),
                        "subscription_period":  product.get("subscription_period"),
                        "next_open_date":       product.get("next_open_date"),
                        "min_purchase_amount":  product.get("min_purchase_amount"),
                        "term":                 product.get("term"),
                        "min_hold_period":      product.get("min_hold_period"),
                        "risk_level":           product.get("risk_level"),
                        "detail_url":           product.get("detail_url"),
                        "prospectus_pdfs":      product.get("prospectus_pdfs", []),
                        "currency_source":      product.get("currency_source"),
                        "source":               "boc_product_metadata",
                    }
            except Exception as e:
                print(f"[Warning] 读取中银理财元数据失败: {e}")

        # 2. 处理标准类型
        if asset_type == 'cn_stock':
            return self._fetch_cn_stock_info_with_priority(symbol)
        elif asset_type == 'cn_fund':
            return self._fetch_cn_fund_info_with_priority(symbol)
        elif asset_type == 'us_equity':
            return self._fetch_us_equity_info(symbol)
        elif asset_type == 'currency':
            # 处理货币对
            return self._fetch_currency_info(symbol)
        # 向后兼容：处理旧类型
        elif asset_type.startswith('cn_fund'):
            return self._fetch_cn_fund_info_with_priority(symbol)
        elif asset_type in ['cn_stock_sh', 'cn_stock_sz']:
            return self._fetch_cn_stock_info_with_priority(symbol)
        return None

    def _fetch_cn_fund_info_with_priority(self, symbol: str) -> Optional[Dict[str, Any]]:
        """根据优先级获取基金信息（优先雪球接口）"""
        if not self.AKSHARE_AVAILABLE:
            return None
        
        # 尝试雪球接口（优先级1）
        try:
            print(f"[API] 尝试雪球接口: {symbol}")
            info_df = ak.fund_individual_basic_info_xq(symbol=symbol)
            if not info_df.empty:
                info_dict = {row['item']: row['value'] for _, row in info_df.iterrows()}
                name = info_dict.get('基金名称', f"基金{symbol}")
                return {
                    'name': name,
                    # 获取到名称后，立即尝试检测币种
                    'currency': self.registry.detect_currency(name),
                    'fund_type_raw': info_dict.get('基金类型', ''),
                    'company': info_dict.get('基金公司', ''),
                    'source': 'akshare_fund_xq'
                }
        except Exception as e:
            print(f"[API Warning] 雪球接口失败 {symbol}: {e}")
        
        # 尝试东方财富接口（优先级2）
        try:
            print(f"[API] 尝试东方财富接口: {symbol}")
            all_funds = ak.fund_name_em()
            row = all_funds[all_funds['基金代码'] == symbol]
            if not row.empty:
                name = row.iloc[0]['基金简称']
                return {
                    'name': name,
                    'currency': self.registry.detect_currency(name),
                    'fund_type_raw': row.iloc[0]['基金类型'],
                    'source': 'akshare_fund_em'
                }
        except Exception as e:
            print(f"[API Warning] 东方财富接口失败 {symbol}: {e}")
        
        return None

    def _fetch_cn_stock_info_with_priority(self, symbol: str) -> Optional[Dict[str, Any]]:
        """获取股票信息"""
        if not self.AKSHARE_AVAILABLE:
            return None
        
        # symbol: sh600519 -> code: 600519
        code = re.search(r'\d{6}', symbol).group(0) if re.search(r'\d{6}', symbol) else symbol
        
        try:
            stock_info_df = ak.stock_info_a_code_name()
            row = stock_info_df[stock_info_df['code'].astype(str) == code]
            if not row.empty:
                return {
                    'name': row.iloc[0]['name'],
                    'currency': 'CNY',
                    'exchange': 'SH' if 'sh' in symbol else 'SZ',
                    'source': 'akshare_stock_info'
                }
        except Exception as e:
            print(f"[API Warning] 股票信息接口失败 {symbol}: {e}")
        
        return None

    def _fetch_us_equity_info(self, symbol: str) -> Optional[Dict[str, Any]]:
        if not self.YFINANCE_AVAILABLE:
            return None
        try:
            import requests
            from requests.adapters import HTTPAdapter
            class SimpleTimeoutAdapter(HTTPAdapter):
                def __init__(self, *args, timeout=2.0, **kwargs):
                    self.timeout = timeout
                    super().__init__(*args, **kwargs)
                def send(self, request, **kwargs):
                    kwargs["timeout"] = self.timeout
                    return super().send(request, **kwargs)

            session = requests.Session()
            adapter = SimpleTimeoutAdapter(timeout=2.0)
            session.mount("https://", adapter)
            session.mount("http://", adapter)

            ticker = yf.Ticker(symbol, session=session)
            info = ticker.info
            if info is None:
                raise ValueError("yfinance返回了空的info")
            return {
                'name': info.get('longName', symbol),
                'currency': 'USD',
                'exchange': info.get('exchange', ''),
                'sector': info.get('sector', ''),
                'source': 'yfinance'
            }
        except Exception as e:
            print(f"[API Warning] yfinance接口失败 {symbol}: {e}")
        return None

    def _fetch_currency_info(self, symbol: str) -> Optional[Dict[str, Any]]:
        """获取货币对信息（智能识别基础货币）"""
        try:
            # 标准化货币对符号
            symbol_upper = symbol.upper()
            
            # 常见货币对映射 - 确定基础货币和计价货币
            currency_pairs = {
                # USD为基础货币
                'USDCNY': ('USD', 'CNY'),  # 1 USD = X CNY
                'USDEUR': ('USD', 'EUR'),
                'USDJPY': ('USD', 'JPY'),
                'USDGBP': ('USD', 'GBP'),
                'USDCAD': ('USD', 'CAD'),
                'USDAUD': ('USD', 'AUD'),
                'USDCHF': ('USD', 'CHF'),
                
                # 反向货币对（基础货币在后）
                'CNYUSD': ('CNY', 'USD'),  # 1 CNY = X USD
                'EURUSD': ('EUR', 'USD'),
                'JPYUSD': ('JPY', 'USD'),
                'GBPUSD': ('GBP', 'USD'),
                'CADUSD': ('CAD', 'USD'),
                'AUDUSD': ('AUD', 'USD'),
                'CHFUSD': ('CHF', 'USD'),
                
                # 交叉货币对
                'EURGBP': ('EUR', 'GBP'),
                'GBPEUR': ('GBP', 'EUR'),
                'EURJPY': ('EUR', 'JPY'),
                'JPYEUR': ('JPY', 'EUR'),
                'GBPJPY': ('GBP', 'JPY'),
                'JPYGBP': ('JPY', 'GBP'),
            }
            
            # 检查是否在支持的货币对列表中
            if symbol_upper in currency_pairs:
                base_currency, quote_currency = currency_pairs[symbol_upper]
                
                # 货币对的币种应该是基础货币（第一个货币）
                # 例如 USDCAD 的币种是 USD，CADUSD 的币种是 CAD
                return {
                    'name': f'{base_currency}/{quote_currency}',
                    'currency': base_currency,  # 关键修复：使用基础货币而不是默认USD
                    'base_currency': base_currency,
                    'quote_currency': quote_currency,
                    'pair_type': 'major' if base_currency == 'USD' or quote_currency == 'USD' else 'cross',
                    'source': 'currency_detector'
                }
            
            # 如果不是标准货币对，尝试智能解析
            if len(symbol_upper) == 6:
                # 假设格式为 FROMTO (如 USDCAD)
                from_currency = symbol_upper[:3]
                to_currency = symbol_upper[3:]
                
                # 验证是否为有效的货币代码
                valid_currencies = {'USD', 'CNY', 'EUR', 'JPY', 'GBP', 'CAD', 'AUD', 'CHF', 'HKD', 'SGD'}
                
                if from_currency in valid_currencies and to_currency in valid_currencies:
                    return {
                        'name': f'{from_currency}/{to_currency}',
                        'currency': from_currency,  # 基础货币
                        'base_currency': from_currency,
                        'quote_currency': to_currency,
                        'pair_type': 'custom',
                        'source': 'currency_detector'
                    }
            
            # 如果不是6位字符，可能是单个货币（如 USD, CNY）
            if len(symbol_upper) == 3:
                valid_currencies = {'USD', 'CNY', 'EUR', 'JPY', 'GBP', 'CAD', 'AUD', 'CHF', 'HKD', 'SGD'}
                if symbol_upper in valid_currencies:
                    return {
                        'name': symbol_upper,
                        'currency': symbol_upper,
                        'base_currency': symbol_upper,
                        'quote_currency': symbol_upper,
                        'pair_type': 'single',
                        'source': 'currency_detector'
                    }
            
            # 无法识别的货币符号，返回默认信息
            return {
                'name': symbol,
                'currency': 'USD',  # 默认回退
                'base_currency': 'USD',
                'quote_currency': 'UNKNOWN',
                'pair_type': 'unknown',
                'source': 'currency_detector'
            }
            
        except Exception as e:
            print(f"[Error] 获取货币信息失败 {symbol}: {e}")
            # 发生错误时返回默认信息
            return {
                'name': symbol,
                'currency': 'USD',
                'base_currency': 'USD',
                'quote_currency': 'UNKNOWN',
                'pair_type': 'error',
                'source': 'currency_detector'
            }

# 便捷入口
def import_asset(symbol: str, asset_type: str, **kwargs):
    return AssetImporter().import_asset(symbol, asset_type, **kwargs)


def get_asset(symbol: str):
    """获取已注册的资产。"""
    registry = AssetRegistry()
    return registry.get_asset(symbol)

if __name__ == "__main__":
    print("=== AssetImporter Test (Smart Currency + Prefix + Cache) ===")
    importer = AssetImporter()
    
    # 测试缓存优先策略
    print("\n1. 第一次导入（应从API获取）:")
    asset1 = importer.import_asset("002892", "cn_fund_qdii", refresh=False)
    
    print("\n2. 第二次导入（应从缓存获取）:")
    asset2 = importer.import_asset("002892", "cn_fund_qdii", refresh=False)
    
    print("\n3. 强制刷新（应从API获取）:")
    asset3 = importer.import_asset("002892", "cn_fund_qdii", refresh=True)
    
    print("\n4. 测试 A股（应自动加前缀）:")
    asset4 = importer.import_asset("600519", "cn_stock_sh", refresh=False)

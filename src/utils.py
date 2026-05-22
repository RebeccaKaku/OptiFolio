# src/utils.py
"""
工具函数集合，包括配置合并、数据处理等辅助函数。
"""

import os
import yaml
from typing import Any, Dict


def deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    """
    递归深度合并两个字典，解决config.update()浅合并问题。
    
    Args:
        base: 基础配置字典
        override: 覆盖配置字典
    
    Returns:
        深度合并后的字典
    """
    result = base.copy()
    
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            # 如果两个都是字典，递归合并
            result[key] = deep_merge(result[key], value)
        else:
            # 否则直接覆盖
            result[key] = value
    
    return result


def load_config_with_deep_merge(public_path: str = "config/settings.yaml", 
                                private_path: str = "config/secrets.yaml") -> Dict[str, Any]:
    """
    加载并深度合并配置。
    
    Args:
        public_path: 公共配置文件路径
        private_path: 私有配置文件路径
    
    Returns:
        合并后的配置字典
    """
    config = {}
    
    # 1. 加载公开配置
    if os.path.exists(public_path):
        with open(public_path, "r", encoding='utf-8') as f:
            config = yaml.safe_load(f)
    else:
        raise FileNotFoundError(f"Public config file not found: {public_path}")
    
    # 2. 加载私密配置 - 如果存在的话
    if os.path.exists(private_path):
        with open(private_path, "r", encoding='utf-8') as f:
            private_conf = yaml.safe_load(f)
            # 深度合并 private_conf 进 config
            if private_conf:
                config = deep_merge(config, private_conf)
    else:
        print(f">>> [Warning] 未找到 {private_path}, 将使用默认/公开配置运行。")
    
    return config


LOCAL_ASSET_NAMES = {
    # 美股
    "AAPL": "苹果公司 (Apple Inc.)",
    "QQQ": "纳斯达克100ETF (Invesco QQQ Trust)",
    "GOOGL": "谷歌 (Alphabet Inc.)",
    "GLD": "黄金ETF (SPDR Gold Shares)",
    "TLT": "20年期以上国债ETF (iShares 20+ Year Treasury Bond ETF)",
    "SGOV": "超短期国债ETF (iShares 0-3 Month Treasury Bond ETF)",
    "MSFT": "微软 (Microsoft Corporation)",
    
    # 中国股票
    "sh600519": "贵州茅台",
    "sh601398": "工商银行",
    "sh601899": "紫金矿业",
    "sh600028": "中国石化",
    "sz000001": "平安银行",
    "sh000001": "上证指数",
    
    # 中国基金
    "510300": "沪深300ETF",
    "005827": "易方达蓝筹精选混合",
    "002892": "华夏恒生ETF联接A",
    "022459": "基金022459",
    "161723": "招商中证白酒指数",
    "000071": "华夏恒生ETF联接C",
    "019599": "基金019599",
    "001235": "基金001235",
    "015282": "基金015282",
    "015283": "基金015283",
    "004502": "基金004502",
    "000198": "基金000198",
    "003537": "基金003537",
    "161226": "国投瑞银白银期货",
    
    # 其他常见资产/汇率对
    "EUR/USD": "欧元/美元",
    "USDCAD": "美元/加元",
    "USD/CAD": "美元/加元",
}


def get_fund_info(symbol: str) -> Dict[str, Any]:
    """
    获取基金基本信息（名称、类型等）。
    使用akshare的fund_name_em接口获取基金信息。
    
    Args:
        symbol: 基金代码
    
    Returns:
        基金信息字典，包含名称、类型等
    """
    # 优先使用本地高速缓存字典
    if symbol in LOCAL_ASSET_NAMES:
        return {
            'symbol': symbol,
            'name': LOCAL_ASSET_NAMES[symbol],
            'fund_type': "未知",
            'pinyin_abbr': '',
            'pinyin_full': ''
        }

    try:
        import akshare as ak
        # 获取所有基金信息
        fund_name_em_df = ak.fund_name_em()
        
        # 查找指定代码的基金
        fund_info = fund_name_em_df[fund_name_em_df['基金代码'] == symbol]
        
        if not fund_info.empty:
            return {
                'symbol': symbol,
                'name': fund_info.iloc[0]['基金简称'],
                'fund_type': fund_info.iloc[0]['基金类型'],
                'pinyin_abbr': fund_info.iloc[0]['拼音缩写'],
                'pinyin_full': fund_info.iloc[0]['拼音全称']
            }
        else:
            # 尝试通过雪球接口获取单只基金信息
            try:
                fund_basic_info = ak.fund_individual_basic_info_xq(symbol=symbol)
                if not fund_basic_info.empty:
                    name = fund_basic_info[fund_basic_info['item'] == '基金名称']['value'].iloc[0]
                    fund_type = fund_basic_info[fund_basic_info['item'] == '基金类型']['value'].iloc[0]
                    return {
                        'symbol': symbol,
                        'name': name,
                        'fund_type': fund_type,
                        'pinyin_abbr': '',
                        'pinyin_full': ''
                    }
            except:
                pass
    except Exception as e:
        print(f"    [Warning] 无法获取基金 {symbol} 信息: {e}")
    
    # 返回默认信息
    return {
        'symbol': symbol,
        'name': f"基金{symbol}",
        'fund_type': "未知",
        'pinyin_abbr': '',
        'pinyin_full': ''
    }


def get_stock_info(symbol: str) -> Dict[str, Any]:
    """
    获取股票基本信息（名称、交易所等）。
    使用akshare的stock_info_a_code_name接口获取股票信息。
    
    Args:
        symbol: 股票代码（可能带sh/sz前缀）
    
    Returns:
        股票信息字典，包含名称、交易所等
    """
    # 优先使用本地高速缓存字典
    if symbol in LOCAL_ASSET_NAMES:
        exchange = 'SH' if symbol.lower().startswith('sh') else 'SZ' if symbol.lower().startswith('sz') else 'Unknown'
        return {
            'symbol': symbol,
            'name': LOCAL_ASSET_NAMES[symbol],
            'exchange': exchange,
            'asset_type': 'stock'
        }

    # 提取纯数字代码（如果有前缀）
    import re
    pure_symbol = symbol.lower()
    if pure_symbol.startswith('sh') or pure_symbol.startswith('sz'):
        # 去掉前缀获取纯数字代码
        code_match = re.search(r'\d{6}', pure_symbol)
        if code_match:
            pure_symbol = code_match.group(0)
    
    try:
        import akshare as ak
        # 获取所有A股股票信息
        stock_info_df = ak.stock_info_a_code_name()
        
        # 查找指定代码的股票
        stock_info = stock_info_df[stock_info_df['code'].astype(str) == pure_symbol]
        
        if not stock_info.empty:
            # 根据原始symbol判断交易所
            exchange = 'SH' if symbol.lower().startswith('sh') else 'SZ' if symbol.lower().startswith('sz') else 'Unknown'
            return {
                'symbol': symbol,  # 保持原始symbol（可能带前缀）
                'name': stock_info.iloc[0]['name'],
                'exchange': exchange,
                'asset_type': 'stock'
            }
        else:
            # 尝试使用实时行情接口获取名称
            try:
                from src.data_core.fetchers.cn_stock import CnStockFetcher
                fetcher = CnStockFetcher()
                quote = fetcher.get_realtime_quote(symbol)
                if quote and 'name' in quote and quote['name']:
                    exchange = 'SH' if symbol.lower().startswith('sh') else 'SZ' if symbol.lower().startswith('sz') else 'Unknown'
                    return {
                        'symbol': symbol,
                        'name': quote['name'],
                        'exchange': exchange,
                        'asset_type': 'stock'
                    }
            except:
                pass
    except Exception as e:
        print(f"    [Warning] 无法获取股票 {symbol} 信息: {e}")
    
    # 返回默认信息
    exchange = 'SH' if symbol.lower().startswith('sh') else 'SZ' if symbol.lower().startswith('sz') else 'Unknown'
    return {
        'symbol': symbol,
        'name': f"股票{symbol}",
        'exchange': exchange,
        'asset_type': 'stock'
    }


def get_asset_info(symbol: str, asset_type: str = None) -> Dict[str, Any]:
    """
    获取资产基本信息（自动识别类型）。
    
    Args:
        symbol: 资产代码（可能带sh/sz前缀）
        asset_type: 可选，资产类型，如果为None则自动判断
    
    Returns:
        资产信息字典
    """
    # 优先尝试本地高速缓存字典，避免同步阻塞的网络/API请求
    if symbol in LOCAL_ASSET_NAMES:
        return {
            'symbol': symbol,
            'name': LOCAL_ASSET_NAMES[symbol],
            'asset_type': asset_type or 'unknown'
        }
    
    for k, v in LOCAL_ASSET_NAMES.items():
        if k.lower() == symbol.lower():
            return {
                'symbol': symbol,
                'name': v,
                'asset_type': asset_type or 'unknown'
            }

    # 创建带有超时设置的 Session 以免请求 yfinance info 挂起
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

    # 如果提供了asset_type，优先使用
    if asset_type:
        # 根据类型调用相应函数
        if asset_type in ['cn_stock', 'cn_equity', 'a_share', 'cn_stock_sh', 'cn_stock_sz']:
            return get_stock_info(symbol)
        elif asset_type in ['cn_fund_etf', 'cn_fund_open', 'cn_fund_qdii', 'cn_fund']:
            return get_fund_info(symbol)
        elif asset_type in ['us_equity', 'us_stock']:
            # 美股信息 - 可以使用yfinance
            try:
                import yfinance as yf
                ticker = yf.Ticker(symbol, session=session)
                info = ticker.info
                if info is None:
                    raise ValueError("yfinance返回了空的info对象")
                return {
                    'symbol': symbol,
                    'name': info.get('longName', symbol),
                    'exchange': info.get('exchange', 'Unknown'),
                    'sector': info.get('sector', 'Unknown'),
                    'industry': info.get('industry', 'Unknown'),
                    'asset_type': 'us_equity'
                }
            except Exception as e:
                print(f"    [Warning] 无法获取美股 {symbol} 信息 (将使用默认名字): {e}")
                return {
                    'symbol': symbol,
                    'name': symbol,
                    'exchange': 'Unknown',
                    'asset_type': 'us_equity'
                }
        else:
            # 默认返回
            return {
                'symbol': symbol,
                'name': symbol,
                'asset_type': asset_type or 'unknown'
            }
    
    # 自动判断资产类型（如果未提供asset_type）
    symbol_lower = symbol.lower()
    
    # 检查是否是带前缀的中国股票
    if symbol_lower.startswith('sh') or symbol_lower.startswith('sz'):
        # 带前缀的中国股票
        return get_stock_info(symbol)
    # 检查是否是纯数字（可能是中国股票或基金）
    elif symbol.isdigit():
        # 长度为6位数字，可能是中国股票
        if len(symbol) == 6:
            # 可能是中国股票，也可能是基金代码
            # 优先尝试股票，如果失败再尝试基金
            try:
                import akshare as ak
                stock_info_df = ak.stock_info_a_code_name()
                if symbol in stock_info_df['code'].astype(str).values:
                    return get_stock_info(symbol)
                else:
                    # 不是股票，尝试基金
                    return get_fund_info(symbol)
            except:
                # 默认按股票处理
                return get_stock_info(symbol)
        else:
            # 非6位数字，可能是基金
            return get_fund_info(symbol)
    # 检查是否是纯字母（可能是美股）
    elif symbol.isalpha():
        # 美股
        try:
            import yfinance as yf
            ticker = yf.Ticker(symbol, session=session)
            info = ticker.info
            if info is None:
                raise ValueError("yfinance返回了空的info对象")
            return {
                'symbol': symbol,
                'name': info.get('longName', symbol),
                'exchange': info.get('exchange', 'Unknown'),
                'sector': info.get('sector', 'Unknown'),
                'industry': info.get('industry', 'Unknown'),
                'asset_type': 'us_equity'
            }
        except Exception as e:
            print(f"    [Warning] 无法获取美股 {symbol} 信息 (将使用默认名字): {e}")
            return {
                'symbol': symbol,
                'name': symbol,
                'exchange': 'Unknown',
                'asset_type': 'us_equity'
            }
    else:
        # 混合代码（数字 and 字母）默认为基金
        return get_fund_info(symbol)


def update_asset_names_in_config(config: Dict[str, Any]) -> Dict[str, Any]:
    """
    更新配置中资产的名称信息。
    
    Args:
        config: 原始配置
    
    Returns:
        更新后的配置
    """
    if 'universe' not in config or 'assets' not in config['universe']:
        return config
    
    updated_assets = []
    for asset in config['universe']['assets']:
        symbol = asset['symbol']
        asset_type = asset.get('type')
        
        # 如果名称不存在或以'（待获取）'开头，尝试获取名称
        current_name = asset.get('name', '')
        if not current_name or current_name.startswith('（待获取）'):
            # 使用新的get_asset_info函数，支持多种资产类型
            asset_info = get_asset_info(symbol, asset_type)
            asset['name'] = asset_info['name']
            print(f"    [Info] 更新资产名称: {symbol} -> {asset_info['name']}")
        else:
            # 名称已存在，确保它是字符串
            if not isinstance(current_name, str):
                asset['name'] = str(current_name)
        
        updated_assets.append(asset)
    
    config['universe']['assets'] = updated_assets
    return config

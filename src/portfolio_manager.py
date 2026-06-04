"""
Legacy portfolio manager. DEPRECATED — use src/core/valuation.py
(ValuationEngine) and src/services/portfolio_service_v2.py instead.
"""

import sys
import os
import yaml
import pandas as pd
from datetime import datetime, timedelta

# === 路径自适应补丁 ===
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# 导入工厂
try:
    from src.data_core.fetchers.factory import get_factory
    from src.data_core.fetchers.currency import CurrencyFetcher
except ImportError:
    print(">>> [System] 导入 Fetcher 失败，请检查文件路径")
    raise


class PortfolioManager:
    def __init__(self, config_path=None, base_currency="CNY"):
        """
        :param base_currency: 投资组合的基准货币，默认 'CNY' (人民币)
        """
        if config_path is None:
            config_path = os.path.join(project_root, "config", "portfolio.yaml")
        
        # 加载设置，获取资产的 currency 属性
        self.settings_path = os.path.join(project_root, "config", "settings.yaml")
        self.asset_meta = self._load_asset_metadata()
        self.asset_type_meta = self._load_asset_type_metadata()  # 新增：资产类型映射
        
        self.config_path = config_path
        self.base_currency = base_currency
        self.holdings = {}
        self.cash = {}
        
        # 使用工厂获取fetcher
        self.factory = get_factory()
        self.fx_fetcher = CurrencyFetcher()
        
        self._load_portfolio()

    def _load_asset_metadata(self):
        """从 settings.yaml 或 candidates.yaml 加载资产元数据(主要为了知道谁是USD谁是CNY)"""
        meta = {}
        
        # 首先尝试从 candidates.yaml 加载
        candidates_path = os.path.join(project_root, "config", "candidates.yaml")
        if os.path.exists(candidates_path):
            try:
                with open(candidates_path, 'r', encoding='utf-8') as f:
                    data = yaml.safe_load(f)
                    if data and 'candidates' in data and 'assets' in data['candidates']:
                        for asset in data['candidates']['assets']:
                            symbol = asset['symbol']
                            # 从 asset_type 推断货币
                            asset_type = asset.get('asset_type', 'us_equity')
                            if asset_type.startswith('cn'):
                                currency = 'CNY'
                            elif asset_type == 'us_equity':
                                currency = 'USD'
                            else:
                                currency = 'USD'  # 默认
                            meta[symbol] = currency
            except Exception as e:
                print(f"    [Warning] 加载 candidates.yaml 失败: {e}")
        
        # 然后尝试从 settings.yaml 加载（向后兼容）
        if os.path.exists(self.settings_path):
            try:
                with open(self.settings_path, 'r', encoding='utf-8') as f:
                    data = yaml.safe_load(f)
                    if data and 'universe' in data and 'assets' in data['universe']:
                        for asset in data['universe']['assets']:
                            symbol = asset['symbol']
                            currency = asset.get('currency', 'USD')
                            meta[symbol] = currency  # 覆盖或新增
            except Exception as e:
                print(f"    [Warning] 加载 settings.yaml 失败: {e}")
        
        return meta
    
    def _load_asset_type_metadata(self):
        """从 candidates.yaml 或 settings.yaml 加载资产类型元数据"""
        meta = {}
        
        # 首先尝试从 candidates.yaml 加载
        candidates_path = os.path.join(project_root, "config", "candidates.yaml")
        if os.path.exists(candidates_path):
            try:
                with open(candidates_path, 'r', encoding='utf-8') as f:
                    data = yaml.safe_load(f)
                    if data and 'candidates' in data and 'assets' in data['candidates']:
                        for asset in data['candidates']['assets']:
                            symbol = asset['symbol']
                            asset_type = asset.get('asset_type', 'us_equity')
                            meta[symbol] = asset_type
            except Exception as e:
                print(f"    [Warning] 加载 candidates.yaml 资产类型失败: {e}")
        
        # 然后尝试从 settings.yaml 加载（向后兼容）
        if os.path.exists(self.settings_path):
            try:
                with open(self.settings_path, 'r', encoding='utf-8') as f:
                    data = yaml.safe_load(f)
                    if data and 'universe' in data and 'assets' in data['universe']:
                        for asset in data['universe']['assets']:
                            symbol = asset['symbol']
                            asset_type = asset.get('asset_type', 'us_equity')
                            meta[symbol] = asset_type  # 覆盖或新增
            except Exception as e:
                print(f"    [Warning] 加载 settings.yaml 资产类型失败: {e}")
        
        return meta

    def _load_portfolio(self):
        """加载持仓文件"""
        if not os.path.exists(self.config_path):
            print(f"    [Error] 找不到 {self.config_path}")
            return

        with open(self.config_path, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)
            # 现金部分：支持多种货币
            self.cash = data.get('cash', {})
            self.holdings = data.get('positions', {})

    def _get_fx_rate(self, from_currency: str, to_currency: str) -> float:
        """
        使用 CurrencyFetcher 获取汇率
        """
        if from_currency == to_currency:
            return 1.0
        
        return self.fx_fetcher.get_realtime_rate(from_currency, to_currency)

    def _get_asset_price(self, symbol: str, asset_currency: str):
        """
        获取资产最新价格
        """
        # 设置合理的日期范围（最近30天）
        end_date = datetime.now().strftime("%Y-%m-%d")
        start_date = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
        
        # 获取资产类型
        asset_type = self.asset_type_meta.get(symbol, 'us_equity')
        
        # 使用工厂获取对应的fetcher
        fetcher = self.factory.get_fetcher(asset_type)
        if fetcher is None:
            print(f"    [Error] 无法获取 {symbol} 的fetcher (类型: {asset_type})")
            return None
        
        try:
            # 调用fetch方法获取数据
            df = fetcher.fetch(symbol, start_date=start_date, end_date=end_date)
            
            if df is not None and not df.empty and 'Close' in df.columns:
                return float(df['Close'].iloc[-1])
            elif df is not None and not df.empty and 'close' in df.columns:
                return float(df['close'].iloc[-1])
            elif df is not None and not df.empty and len(df.columns) > 0:
                # 获取最后一列的最新值
                return float(df.iloc[:, -1].iloc[-1])
            else:
                print(f"    [Warning] {symbol} 无有效数据")
                return None
        except Exception as e:
            print(f"    [Error] 获取 {symbol} 价格失败: {e}")
            return None

    def get_current_valuation(self):
        print(f">>> [Portfolio] 计算持仓市值 (基准货币: {self.base_currency})...")
        
        valuation_data = []
        total_market_value = 0.0
        
        # 打印支持的货币对
        print(f"    [汇率] 支持的货币对: {', '.join(self.fx_fetcher.get_supported_pairs()[:5])}...")
        
        for symbol, shares in self.holdings.items():
            symbol = str(symbol)
            # 1. 确定该资产的原币种
            asset_currency = self.asset_meta.get(symbol, "USD")
            
            # 2. 获取资产价格
            raw_price = self._get_asset_price(symbol, asset_currency)
            
            if raw_price is not None:
                # 3. 汇率换算
                fx_rate = self._get_fx_rate(asset_currency, self.base_currency)
                
                # 4. 计算价值
                price_in_base = raw_price * fx_rate
                position_value = shares * price_in_base
                total_market_value += position_value
                
                valuation_data.append({
                    "Symbol": symbol,
                    "Shares": shares,
                    "Orig Ccy": asset_currency,
                    "Orig Price": round(raw_price, 2),
                    "FX Rate": round(fx_rate, 4),
                    "Price (Base)": round(price_in_base, 2),
                    "Value (Base)": round(position_value, 2)
                })
                print(f"    [√] {symbol}: {shares}股 × {raw_price:.2f} {asset_currency} × {fx_rate:.4f} = {position_value:.2f} {self.base_currency}")
            else:
                print(f"    [×] {symbol} 无法获取价格")

        # 处理现金
        cash_in_base = 0.0
        for currency, amount in self.cash.items():
            if currency == self.base_currency:
                fx_rate = 1.0
            else:
                fx_rate = self._get_fx_rate(currency, self.base_currency)
            cash_amount = amount * fx_rate
            cash_in_base += cash_amount
            print(f"    [现金] {amount:.2f} {currency} × {fx_rate:.4f} = {cash_amount:.2f} {self.base_currency}")
        
        total_equity = total_market_value + cash_in_base
        
        # 生成报表
        if valuation_data:
            df_val = pd.DataFrame(valuation_data)
            df_val['Weight'] = df_val['Value (Base)'] / total_equity
            
            print(f"\n=== 当前持仓 (以 {self.base_currency} 计价) ===")
            print(f"现金总额: {cash_in_base:,.2f} {self.base_currency}")
            
            pd.set_option('display.max_columns', None)
            pd.set_option('display.width', 1000)
            
            # 格式化输出
            format_dict = {
                'Weight': '{:.2%}',
                'Value (Base)': '{:,.2f}',
                'Price (Base)': '{:,.2f}',
                'Orig Price': '{:,.2f}',
                'FX Rate': '{:.4f}'
            }
            
            # 按价值排序
            df_val = df_val.sort_values('Value (Base)', ascending=False)
            
            if hasattr(df_val, 'style'):
                print(df_val.style.format(format_dict).to_string())
            else:
                # 手动格式化
                for col, fmt in format_dict.items():
                    if col in df_val.columns:
                        if '%' in fmt:
                            df_val[col] = df_val[col].apply(lambda x: fmt.format(x))
                        else:
                            df_val[col] = df_val[col].apply(lambda x: fmt.format(x) if pd.notnull(x) else '')
                print(df_val.to_string(index=False))
            
            print("-" * 60)
            print(f"总资产: {total_equity:,.2f} {self.base_currency}")
            
            # 计算资产类别分布
            if not df_val.empty:
                print("\n=== 资产类别分布 ===")
                df_val['Asset Type'] = df_val['Symbol'].apply(
                    lambda x: '中国资产' if str(x)[0].isdigit() else '美国资产'
                )
                type_dist = df_val.groupby('Asset Type')['Value (Base)'].sum()
                for asset_type, value in type_dist.items():
                    pct = value / total_equity
                    print(f"  {asset_type}: {value:,.2f} {self.base_currency} ({pct:.2%})")
        else:
            print("    [信息] 无持仓数据")
        
        return total_equity

    def test_currency_fetcher(self):
        """
        测试 CurrencyFetcher 功能
        """
        print(">>> [Test] 测试货币汇率获取...")
        
        # 测试主要货币对
        test_pairs = [
            ("USD", "CNY"),
            ("CNY", "USD"),
            ("USD", "EUR"),
            ("EUR", "USD"),
            ("USD", "JPY"),
            ("GBP", "USD"),
        ]
        
        for from_ccy, to_ccy in test_pairs:
            rate = self._get_fx_rate(from_ccy, to_ccy)
            print(f"    {from_ccy}/{to_ccy}: {rate:.4f}")
        
        print(">>> [Test] 测试完成")


if __name__ == "__main__":
    # 测试不同基准货币
    print("=" * 60)
    print("FM Portfolio Manager - 多货币支持版")
    print("=" * 60)
    
    # 以 CNY 为基准
    print("\n1. 以 CNY 为基准货币:")
    pm_cny = PortfolioManager(base_currency="CNY")
    pm_cny.test_currency_fetcher()
    total_cny = pm_cny.get_current_valuation()
    
    print("\n" + "=" * 60)
    
    # 以 USD 为基准
    print("\n2. 以 USD 为基准货币:")
    pm_usd = PortfolioManager(base_currency="USD")
    pm_usd.test_currency_fetcher()
    total_usd = pm_usd.get_current_valuation()
    
    print("\n" + "=" * 60)
    print("测试完成!")
    print(f"总资产: {total_cny:,.2f} CNY ≈ {total_usd:,.2f} USD")
# src/data_core/fetchers/currency.py
"""
Currency/Forex data fetcher using yfinance.
Supports major currency pairs: USD, CNY, EUR, GBP, JPY, CAD, etc.
"""
import yfinance as yf
import pandas as pd
from src.data_core.interface import BaseFetcher


class CurrencyFetcher(BaseFetcher):
    """
    Fetcher for foreign exchange rates.
    
    Symbol format: "FROMTO" where FROM and TO are 3-letter currency codes.
    Example: "USDCNY" for USD to CNY rate.
    
    Returns DataFrame with OHLC data (Open, High, Low, Close, Volume).
    The 'Close' column represents the exchange rate.
    """
    
    # Mapping from currency pair to yfinance symbol
    # yfinance uses format like "USDCNY=X" for USD/CNY
    # Some pairs have different conventions
    _SYMBOL_MAP = {
        # Direct pairs
        "USDCNY": "CNY=X",        # USD to CNY
        "CNYUSD": "CNYUSD=X",     # CNY to USD (inverse)
        "USDEUR": "EUR=X",        # USD to EUR
        "EURUSD": "EURUSD=X",     # EUR to USD
        "USDJPY": "JPY=X",        # USD to JPY
        "JPYUSD": "JPYUSD=X",     # JPY to USD
        "USDGBP": "GBP=X",        # USD to GBP
        "GBPUSD": "GBPUSD=X",     # GBP to USD
        "USDCAD": "CAD=X",        # USD to CAD
        "CADUSD": "CADUSD=X",     # CAD to USD
        "USDAUD": "AUD=X",        # USD to AUD
        "AUDUSD": "AUDUSD=X",     # AUD to USD
        "USDCHF": "CHF=X",        # USD to CHF
        "CHFUSD": "CHFUSD=X",     # CHF to USD
        # Cross rates (can be constructed from USD pairs)
        "EURGBP": "EURGBP=X",     # EUR to GBP
        "GBPEUR": "GBPEUR=X",     # GBP to EUR
        "EURJPY": "EURJPY=X",     # EUR to JPY
        "JPYEUR": "JPYEUR=X",     # JPY to EUR
        "GBPJPY": "GBPJPY=X",     # GBP to JPY
        "JPYGBP": "JPYGBP=X",     # JPY to GBP
    }
    
    def fetch(self, symbol: str, start_date: str, end_date: str, 
              interval: str = "1d") -> pd.DataFrame:
        """
        Fetch historical exchange rate data.
        
        Args:
            symbol: Currency pair in format "FROMTO" (e.g., "USDCNY")
            start_date: Start date in "YYYY-MM-DD" format
            end_date: End date in "YYYY-MM-DD" format
            interval: Data interval ("1d", "1h", etc.)
            
        Returns:
            DataFrame with OHLCV columns, index as DatetimeIndex
        """
        print(f"    [采购-FX] 下载汇率 {symbol} | 区间: {start_date} 至 {end_date}")
        
        # Convert symbol to yfinance format
        yf_symbol = self._get_yfinance_symbol(symbol)
        if yf_symbol is None:
            print(f"    [Error] 不支持的货币对: {symbol}")
            return pd.DataFrame()
        
        try:
            ticker = yf.Ticker(yf_symbol)
            # Fetch historical data
            df = ticker.history(
                start=start_date,
                end=end_date,
                interval=interval,
                auto_adjust=True
            )
            
            if df.empty:
                print(f"    [Warning] 汇率数据为空: {symbol}")
                return pd.DataFrame()
            
            # Clean timezone
            if df.index.tz is not None:
                df.index = df.index.tz_localize(None)
            
            # Ensure we have expected columns
            expected_cols = ['Open', 'High', 'Low', 'Close', 'Volume']
            for col in expected_cols:
                if col not in df.columns:
                    df[col] = pd.NA
            
            return df[expected_cols]
            
        except Exception as e:
            print(f"    [Error] 汇率 {symbol} 下载失败: {e}")
            return pd.DataFrame()
    
    def get_realtime_rate(self, from_currency: str, to_currency: str) -> float:
        """
        Get real-time exchange rate for a currency pair.
        This is a convenience method for portfolio valuation.
        
        Args:
            from_currency: 3-letter currency code (e.g., "USD")
            to_currency: 3-letter currency code (e.g., "CNY")
            
        Returns:
            Exchange rate (how many 'to_currency' per 1 'from_currency')
        """
        if from_currency == to_currency:
            return 1.0
        
        symbol = f"{from_currency}{to_currency}"
        try:
            # Try to get latest data (last 1 day)
            df = self.fetch(symbol, start_date="2024-01-01", end_date="2024-12-31")
            if not df.empty:
                return float(df['Close'].iloc[-1])
        except:
            pass
        
        # Fallback: try inverse pair
        inverse_symbol = f"{to_currency}{from_currency}"
        try:
            df = self.fetch(inverse_symbol, start_date="2024-01-01", end_date="2024-12-31")
            if not df.empty:
                return 1.0 / float(df['Close'].iloc[-1])
        except:
            pass
        
        print(f"    [Warning] 无法获取汇率 {from_currency}/{to_currency}，使用 1.0")
        return 1.0
    
    def _get_yfinance_symbol(self, pair_symbol: str) -> str:
        """Convert our pair symbol to yfinance symbol."""
        # Check direct mapping first
        if pair_symbol in self._SYMBOL_MAP:
            return self._SYMBOL_MAP[pair_symbol]
        
        # If not in map, try generic format
        # yfinance often uses "XXXYYY=X" format
        if len(pair_symbol) == 6:
            return f"{pair_symbol}=X"
        
        return None
    
    @classmethod
    def get_supported_pairs(cls):
        """Return list of supported currency pairs."""
        return list(cls._SYMBOL_MAP.keys())
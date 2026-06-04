import pytest
from src.analytics.exposure import ExposureAnalyzer, ExposureReport, ExposureItem

class MockRegistry:
    def get_asset_info(self, symbol):
        data = {
            'AAPL': {'exists': True, 'asset_type': 'us_equity', 'currency': 'USD'},
            '600519': {'exists': True, 'asset_type': 'cn_stock', 'currency': 'CNY'},
            '000198': {'exists': True, 'asset_type': 'cn_money_market_fund', 'currency': 'CNY'},
            'BOND_FUND': {'exists': True, 'asset_type': 'cn_fund_open', 'fund_type_raw': '债券型'},
            'BTC': {'exists': True, 'asset_type': 'crypto', 'currency': 'USD'}
        }
        return data.get(symbol, {'exists': False})

def test_classify():
    analyzer = ExposureAnalyzer()

    # Equity
    assert analyzer.classify('us_equity') == 'equity'
    assert analyzer.classify('cn_stock') == 'equity'
    assert analyzer.classify('hk_equity') == 'equity'
    assert analyzer.classify('cn_fund_open', {'fund_type_raw': '混合型'}) == 'equity'
    assert analyzer.classify('cn_fund_open', {'fund_type_raw': '股票型'}) == 'equity'

    # Fixed Income
    assert analyzer.classify('cn_fund_bond') == 'fixed_income'
    assert analyzer.classify('cn_fund_open', {'fund_type_raw': '债券型'}) == 'fixed_income'
    assert analyzer.classify('bank_wmp', {'asset_class': 'fixed_income'}) == 'fixed_income'

    # Cash
    assert analyzer.classify('money_fund') == 'cash'
    assert analyzer.classify('cn_money_market_fund') == 'cash'
    assert analyzer.classify('deposit') == 'cash'
    assert analyzer.classify('currency') == 'cash'

    # Alternative
    assert analyzer.classify('crypto') == 'alternative'
    assert analyzer.classify('bank_wmp') == 'alternative'

    # Unknown
    assert analyzer.classify('unknown_type') == 'unknown'

def test_analyze():
    analyzer = ExposureAnalyzer()
    registry = MockRegistry()

    positions = {
        'AAPL': {'value': 1000.0, 'currency': 'USD'},
        '600519': {'value': 2000.0, 'currency': 'CNY'},
        '000198': {'value': 500.0, 'currency': 'CNY'},
        'BOND_FUND': {'value': 1500.0, 'currency': 'CNY'}
    }
    total_value = 5000.0

    report = analyzer.analyze(positions, registry, total_value)

    assert isinstance(report, ExposureReport)
    assert report.total_value == 5000.0

    # Check asset class buckets
    ac_buckets = {item.bucket: item for item in report.by_asset_class}
    assert 'equity' in ac_buckets
    assert ac_buckets['equity'].value == 3000.0  # AAPL (1000) + 600519 (2000)
    assert ac_buckets['equity'].pct == 0.6

    assert 'cash' in ac_buckets
    assert ac_buckets['cash'].value == 500.0  # 000198

    assert 'fixed_income' in ac_buckets
    assert ac_buckets['fixed_income'].value == 1500.0  # BOND_FUND

    # Check currency buckets
    cur_buckets = {item.bucket: item for item in report.by_currency}
    assert 'USD' in cur_buckets
    assert cur_buckets['USD'].value == 1000.0

    assert 'CNY' in cur_buckets
    assert cur_buckets['CNY'].value == 4000.0

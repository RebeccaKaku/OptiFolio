from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional
from datetime import datetime

@dataclass
class ExposureItem:
    dimension: str  # asset_class, currency, region
    bucket: str
    value: float
    pct: float
    asset_ids: List[str] = field(default_factory=list)

@dataclass
class ExposureReport:
    as_of: str
    total_value: float
    by_asset_class: List[ExposureItem]
    by_currency: List[ExposureItem]

class ExposureAnalyzer:
    """
    ExposureAnalyzer provides Level 0 classification and analysis of portfolio exposure.

    Level 0 = product label only, no look-through.
    This means the classification is based on the primary asset type of the product
    rather than analyzing the underlying holdings of a fund or structured product.
    """

    def classify(self, product_type: str, metadata: Optional[Dict[str, Any]] = None) -> str:
        """
        Classify a product into an asset class bucket.

        Rules:
        - us_equity, cn_stock, hk_equity -> equity
        - cn_fund_open (mixed/equity) -> equity
        - cn_fund_open (bond) -> fixed_income
        - cn_money_market_fund, money_fund -> cash
        - bank_wmp -> alternative (or fixed_income if metadata says so)
        - crypto -> alternative
        - deposit -> cash
        - unknown -> unknown
        """
        pt = str(product_type).lower()

        # Metadata-based refinements
        if metadata:
            # bank_wmp -> fixed_income if metadata says so
            if pt == 'bank_wmp' and (metadata.get('fixed_income') or metadata.get('asset_class') == 'fixed_income'):
                return 'fixed_income'

            # cn_fund_open refinements
            if pt == 'cn_fund_open':
                fund_type = metadata.get('fund_type_raw', '') or metadata.get('type', '')
                if any(k in fund_type for k in ['债', '债券', 'bond']):
                    return 'fixed_income'
                if any(k in fund_type for k in ['混合', '股票', '指数', 'mixed', 'equity', 'index']):
                    return 'equity'

        # Basic mapping
        equity_types = [
            'us_equity', 'cn_stock', 'hk_equity',
            'cn_stock_sh', 'cn_stock_sz', 'hk_stock', 'us_stock',
            'cn_fund_etf', 'cn_fund_lof', 'cn_fund_index', 'cn_fund_qdii'
        ]
        if pt in equity_types:
            return 'equity'

        if pt == 'cn_fund_open':
            return 'equity'  # Default for open-end funds

        if pt == 'cn_fund_bond':
            return 'fixed_income'

        cash_types = ['cn_fund_money', 'cn_money_market_fund', 'money_fund', 'deposit', 'cash', 'currency']
        if pt in cash_types:
            return 'cash'

        if pt == 'bank_wmp':
            return 'alternative'

        if pt in ['crypto', 'cryptocurrency']:
            return 'alternative'

        return 'unknown'

    def analyze(self, positions: Dict[str, Dict[str, Any]], product_registry: Any, total_value: float) -> ExposureReport:
        """
        Analyze positions and generate an ExposureReport.

        Args:
            positions: Dict of symbol -> position_info (usually from PortfolioCore.get_portfolio_value)
            product_registry: AssetManager or Registry to get asset metadata for classification
            total_value: Total value of the portfolio for percentage calculation
        """
        asset_class_groups = {}
        currency_groups = {}

        for symbol, pos in positions.items():
            val = pos.get('value', 0.0)
            currency = pos.get('currency', 'UNKNOWN')

            # Try to get more detailed info from registry for better classification
            asset_info = {}
            if product_registry:
                if hasattr(product_registry, 'get_asset_info'):
                    # AssetManager style
                    res = product_registry.get_asset_info(symbol)
                    if res.get('exists'):
                        asset_info = res
                elif hasattr(product_registry, 'get_asset'):
                    # AssetRegistry style
                    asset_def = product_registry.get_asset(symbol)
                    if asset_def:
                        asset_info = asset_def.to_dict()

            product_type = asset_info.get('asset_type') or pos.get('asset_type', 'unknown')

            # Classify into asset class
            asset_class = self.classify(product_type, asset_info)

            # Aggregate by asset class
            if asset_class not in asset_class_groups:
                asset_class_groups[asset_class] = {'value': 0.0, 'assets': []}
            asset_class_groups[asset_class]['value'] += val
            asset_class_groups[asset_class]['assets'].append(symbol)

            # Aggregate by currency
            if currency not in currency_groups:
                currency_groups[currency] = {'value': 0.0, 'assets': []}
            currency_groups[currency]['value'] += val
            currency_groups[currency]['assets'].append(symbol)

        # Build ExposureItems for asset classes
        ac_items = []
        for ac, data in asset_class_groups.items():
            ac_items.append(ExposureItem(
                dimension='asset_class',
                bucket=ac,
                value=data['value'],
                pct=data['value'] / total_value if total_value > 0 else 0,
                asset_ids=data['assets']
            ))
        ac_items.sort(key=lambda x: x.value, reverse=True)

        # Build ExposureItems for currencies
        cur_items = []
        for cur, data in currency_groups.items():
            cur_items.append(ExposureItem(
                dimension='currency',
                bucket=cur,
                value=data['value'],
                pct=data['value'] / total_value if total_value > 0 else 0,
                asset_ids=data['assets']
            ))
        cur_items.sort(key=lambda x: x.value, reverse=True)

        return ExposureReport(
            as_of=datetime.now().isoformat(),
            total_value=total_value,
            by_asset_class=ac_items,
            by_currency=cur_items
        )

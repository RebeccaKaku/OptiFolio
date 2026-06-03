"""PortfolioServiceV2 — date-aware portfolio management.

Integrates ValuationEngine, CorporateActionProcessor, FeeProcessor,
and PortfolioHistoryTracker into a single service facade.

Portfolio loading order (same as the existing convention):
1. ``OPTIFOLIO_PORTFOLIO_PATH`` env var
2. ``local/portfolio.yaml``
3. ``config/portfolio.yaml`` (legacy)
"""

from __future__ import annotations

import os
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from src.core.corporate_actions import CorporateActionProcessor
from src.core.fees import FeeProcessor
from src.core.paths import PROJECT_ROOT
from src.core.portfolio_history import PortfolioHistoryTracker
from src.core.valuation import (
    FxRateProvider,
    NoPriceDataError,
    ValuationEngine,
)
from src.data_foundation.repository import MarketDataRepository
from src.analytics.concentration import ConcentrationAnalyzer
from src.analytics.fx_exposure import FxExposureAnalyzer
from src.analytics.liquidity import LiquidityAnalyzer
from src.domain import ProductDefinition, ValuationRequest


class PortfolioServiceV2:
    """Date-aware portfolio management service.

    Usage::

        svc = PortfolioServiceV2()
        result = svc.get_value(as_of=date(2025, 6, 15))  # next-day NAV
        history = svc.get_value_history(start=date(2025, 1, 1), end=date(2025, 6, 15))
        svc.record_dividend("AAPL", date(2025, 6, 15), amount_per_share=0.50)
    """

    def __init__(
        self,
        valuation_engine: Optional[ValuationEngine] = None,
        corp_action_processor: Optional[CorporateActionProcessor] = None,
        fee_processor: Optional[FeeProcessor] = None,
        history_tracker: Optional[PortfolioHistoryTracker] = None,
        config_path: Optional[Path] = None,
        base_currency: str = "CNY",
        fx_exposure_analyzer: Optional[FxExposureAnalyzer] = None,
        concentration_analyzer: Optional[ConcentrationAnalyzer] = None,
        liquidity_analyzer: Optional[LiquidityAnalyzer] = None,
    ):
        self.valuation_engine = valuation_engine or self._default_valuation_engine()
        self.corp_actions = corp_action_processor or CorporateActionProcessor()
        self.fee_processor = fee_processor or FeeProcessor()
        self.history = history_tracker or PortfolioHistoryTracker()
        self.config_path = config_path or self._resolve_config_path()
        self.base_currency = base_currency
        self._fx_analyzer = fx_exposure_analyzer or FxExposureAnalyzer()
        self._concentration_analyzer = concentration_analyzer or ConcentrationAnalyzer()
        self._liquidity_analyzer = liquidity_analyzer or LiquidityAnalyzer()
        self._holdings: Dict[str, float] = {}
        self._cash: Dict[str, float] = {}
        self._load_portfolio()

    # ── public API ─────────────────────────────────────────────────────

    def get_value(
        self,
        as_of: Optional[date] = None,
        base_currency: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Value the portfolio as of a given date (next-day NAV).

        When ``as_of`` is None, defaults to today.
        """
        target_date = as_of or date.today()
        currency = base_currency or self.base_currency

        try:
            result = self.valuation_engine.value(
                self._holdings, self._cash,
                ValuationRequest(as_of=target_date, base_currency=currency),
            )
            self.history.record(result)
            return {"success": True, "data": result.to_dict(), "message": "Valuation complete"}
        except NoPriceDataError as exc:
            return {"success": False, "message": str(exc), "error_code": "NO_PRICE_DATA"}
        except Exception as exc:
            return {"success": False, "message": str(exc), "error_code": "VALUATION_ERROR"}

    def get_value_history(
        self,
        start: date,
        end: date,
        base_currency: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Daily valuation over a date range.

        Corporate actions are applied incrementally: for each date in the
        range, only actions with ex_date <= that date are applied. This
        ensures holdings reflect the correct state at each point in time.
        """
        currency = base_currency or self.base_currency

        import pandas as pd
        dates = pd.bdate_range(start=start, end=end).tolist()
        date_list = sorted([d.date() for d in dates])

        results = []
        for d in date_list:
            # Apply corporate actions up to this specific date
            adj_holdings, adj_cash, _ = self.corp_actions.apply_to_holdings(
                self._holdings, self._cash, up_to_date=d,
            )
            try:
                result = self.valuation_engine.value(
                    adj_holdings, adj_cash,
                    ValuationRequest(as_of=d, base_currency=currency),
                )
                results.append(result)
            except NoPriceDataError:
                continue

        return {
            "success": True,
            "data": {
                "base_currency": currency,
                "start": start.isoformat(),
                "end": end.isoformat(),
                "records": [r.to_dict() for r in results],
            },
            "message": f"Valuation history from {start} to {end}",
        }

    def get_current_holdings(self) -> Dict[str, Any]:
        """Return current holdings snapshot."""
        return {
            "success": True,
            "data": {
                "holdings": dict(self._holdings),
                "cash": dict(self._cash),
                "base_currency": self.base_currency,
            },
        }

    def get_cash_balances(self) -> Dict[str, Any]:
        """Return cash balances by currency."""
        return {
            "success": True,
            "data": {"cash": dict(self._cash), "base_currency": self.base_currency},
        }

    def get_fx_exposure_report(
        self,
        as_of: Optional[date] = None,
        base_currency: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Return FX exposure analysis for the portfolio.

        Aggregates positions and cash by currency, computes each currency's
        percentage of total portfolio value, and estimates sensitivity to
        a 1% FX rate move.
        """
        currency = base_currency or self.base_currency
        target_date = as_of or date.today()

        try:
            result = self.valuation_engine.value(
                self._holdings, self._cash,
                ValuationRequest(as_of=target_date, base_currency=currency),
            )
            report = self._fx_analyzer.analyze(
                positions=result.positions,
                cash_breakdown=result.cash_breakdown,
                base_currency=currency,
                total_value=result.total_value,
            )
        except NoPriceDataError as exc:
            return {"success": False, "message": str(exc), "error_code": "NO_PRICE_DATA"}
        except Exception as exc:
            return {"success": False, "message": str(exc), "error_code": "FX_EXPOSURE_ERROR"}

        return {"success": True, "data": report.to_dict(), "message": "FX exposure computed"}

    def get_concentration_report(
        self,
        as_of: Optional[date] = None,
        base_currency: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Return concentration risk analysis across currency, asset class, and issuer.

        Computes breakdowns of portfolio value by currency, mapped asset class,
        and issuer/manager. Includes threshold-based warnings in Chinese for
        actionable risk alerts.
        """
        currency = base_currency or self.base_currency
        target_date = as_of or date.today()

        try:
            result = self.valuation_engine.value(
                self._holdings, self._cash,
                ValuationRequest(as_of=target_date, base_currency=currency),
            )
            asset_meta = self._load_asset_meta()
            report = self._concentration_analyzer.analyze(
                positions=result.positions,
                asset_meta=asset_meta,
            )
        except NoPriceDataError as exc:
            return {"success": False, "message": str(exc), "error_code": "NO_PRICE_DATA"}
        except Exception as exc:
            return {"success": False, "message": str(exc), "error_code": "CONCENTRATION_ERROR"}

        return {"success": True, "data": report.to_dict(), "message": "Concentration risk computed"}

    def get_liquidity_report(
        self,
        as_of: Optional[date] = None,
        base_currency: Optional[str] = None,
        product_registry: Optional[Dict[str, ProductDefinition]] = None,
    ) -> Dict[str, Any]:
        """Return liquidity risk analysis by redemption timeline.

        Classifies every position into a liquidity bucket (T+0 through 锁仓)
        using product metadata, symbol-pattern heuristics, and lockup dates.
        Returns the percentage of portfolio available within 7 days and the
        percentage locked long-term.
        """
        currency = base_currency or self.base_currency
        target_date = as_of or date.today()
        registry = product_registry or self._load_product_registry()

        try:
            result = self.valuation_engine.value(
                self._holdings, self._cash,
                ValuationRequest(as_of=target_date, base_currency=currency),
            )
            report = self._liquidity_analyzer.analyze(
                positions=result.positions,
                product_registry=registry,
                total_value=result.total_value,
                cash_breakdown=result.cash_breakdown,
            )
        except NoPriceDataError as exc:
            return {"success": False, "message": str(exc), "error_code": "NO_PRICE_DATA"}
        except Exception as exc:
            return {"success": False, "message": str(exc), "error_code": "LIQUIDITY_ERROR"}

        return {"success": True, "data": report.to_dict(), "message": "Liquidity analysis complete"}

    def get_risk_rules(
        self,
        as_of: Optional[date] = None,
        base_currency: Optional[str] = None,
        user_targets: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Run the risk rule engine across all dimensions.

        Performs a single valuation, then runs liquidity, concentration, and
        FX exposure analyzers.  Feeds the typed reports to the rule engine and
        returns each rule result plus an aggregate summary.

        Args:
            as_of: Valuation date (defaults to today).
            base_currency: Reporting currency (defaults to service default).
            user_targets: Optional user-configured thresholds.
                Supported keys: ``emergency_months``, ``monthly_spending``,
                ``fx_target_pct``.

        Returns:
            ``{"success": True, "data": {"rules": [...], "summary": {...}}}``
        """
        from src.analytics.rule_engine import RuleEngine

        currency = base_currency or self.base_currency
        target_date = as_of or date.today()

        try:
            result = self.valuation_engine.value(
                self._holdings, self._cash,
                ValuationRequest(as_of=target_date, base_currency=currency),
            )
        except NoPriceDataError as exc:
            return {"success": False, "message": str(exc), "error_code": "NO_PRICE_DATA"}
        except Exception as exc:
            return {"success": False, "message": str(exc), "error_code": "VALUATION_ERROR"}

        portfolio_value = result.total_value

        # ── Run analyzers (each is lenient with empty inputs) ────────────
        liquidity_report = None
        concentration_report = None
        fx_exposure_report = None

        try:
            registry = self._load_product_registry()
            liquidity_report = self._liquidity_analyzer.analyze(
                positions=result.positions,
                product_registry=registry,
                total_value=portfolio_value,
                cash_breakdown=result.cash_breakdown,
            )
        except Exception:
            pass

        try:
            asset_meta = self._load_asset_meta()
            concentration_report = self._concentration_analyzer.analyze(
                positions=result.positions,
                asset_meta=asset_meta,
            )
        except Exception:
            pass

        try:
            fx_exposure_report = self._fx_analyzer.analyze(
                positions=result.positions,
                cash_breakdown=result.cash_breakdown,
                base_currency=currency,
                total_value=portfolio_value,
            )
        except Exception:
            pass

        # ── Run rules ────────────────────────────────────────────────────
        rules = RuleEngine.run_from_reports(
            liquidity_report=liquidity_report,
            concentration_report=concentration_report,
            fx_exposure_report=fx_exposure_report,
            portfolio_value=portfolio_value,
            base_currency=currency,
            user_targets=user_targets,
        )
        summary = RuleEngine.summary(rules)

        return {
            "success": True,
            "data": {
                "as_of": target_date.isoformat(),
                "base_currency": currency,
                "portfolio_value": portfolio_value,
                "rules": [r.to_dict() for r in rules],
                "summary": summary,
            },
            "message": f"Risk rules evaluated ({len(rules)} rules, {summary['failed']} failed)",
        }

    # ── corporate actions ──────────────────────────────────────────────

    def record_dividend(
        self,
        asset_id: str,
        ex_date: date,
        amount_per_share: float,
        currency: str = "USD",
        effective_date: Optional[date] = None,
        withholding_tax_rate: float = 0.0,
    ) -> Dict[str, Any]:
        """Record a cash dividend."""
        action = self.corp_actions.record_dividend(
            asset_id=asset_id,
            ex_date=ex_date,
            amount_per_share=amount_per_share,
            currency=currency,
            effective_date=effective_date,
            withholding_tax_rate=withholding_tax_rate,
        )
        return {"success": True, "data": action.to_dict(), "message": "Dividend recorded"}

    def record_split(
        self,
        asset_id: str,
        ex_date: date,
        ratio: float,
        effective_date: Optional[date] = None,
    ) -> Dict[str, Any]:
        """Record a stock split."""
        action = self.corp_actions.record_split(
            asset_id=asset_id,
            ex_date=ex_date,
            ratio=ratio,
            effective_date=effective_date,
        )
        return {"success": True, "data": action.to_dict(), "message": "Stock split recorded"}

    def record_merger(
        self,
        asset_id: str,
        target_asset_id: str,
        ex_date: date,
        exchange_ratio: float,
        cash_per_share: float = 0.0,
        cash_currency: str = "USD",
        effective_date: Optional[date] = None,
    ) -> Dict[str, Any]:
        """Record a merger/acquisition."""
        action = self.corp_actions.record_merger(
            asset_id=asset_id,
            target_asset_id=target_asset_id,
            ex_date=ex_date,
            exchange_ratio=exchange_ratio,
            cash_per_share=cash_per_share,
            cash_currency=cash_currency,
            effective_date=effective_date,
        )
        return {"success": True, "data": action.to_dict(), "message": "Merger recorded"}

    def get_corporate_actions(
        self,
        asset_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """List recorded corporate actions."""
        actions = self.corp_actions.list_all()
        if asset_id:
            actions = [a for a in actions if a.get("asset_id") == asset_id]
        return {"success": True, "data": {"actions": actions}, "message": "Actions retrieved"}

    # ── metrics ────────────────────────────────────────────────────────

    def compute_metrics(self) -> Dict[str, Any]:
        """Compute performance metrics from tracked history."""
        try:
            metrics = self.history.compute_metrics()
            return {"success": True, "data": metrics, "message": "Metrics computed"}
        except Exception as exc:
            return {"success": False, "message": str(exc), "error_code": "METRICS_ERROR"}

    def get_history(
        self,
        start: Optional[date] = None,
        end: Optional[date] = None,
    ) -> Dict[str, Any]:
        """Return tracked portfolio history."""
        df = self.history.get_history(start, end)
        records = []
        if not df.empty:
            records = df.to_dict(orient="records")
            for r in records:
                if "date" in r and hasattr(r["date"], "isoformat"):
                    r["date"] = r["date"].isoformat()
        return {
            "success": True,
            "data": {"records": records, "count": len(records)},
            "message": "History retrieved",
        }

    # ── internal ───────────────────────────────────────────────────────

    @staticmethod
    def _default_valuation_engine() -> ValuationEngine:
        return ValuationEngine(
            market_data=MarketDataRepository(),
            fx_provider=FxRateProvider(),
        )

    @staticmethod
    def _resolve_config_path() -> Path:
        env_path = os.environ.get("OPTIFOLIO_PORTFOLIO_PATH")
        if env_path:
            return Path(env_path)

        local_path = PROJECT_ROOT / "local" / "portfolio.yaml"
        if local_path.exists():
            return local_path

        return PROJECT_ROOT / "config" / "portfolio.yaml"

    def _load_asset_meta(self) -> Dict[str, Dict[str, Any]]:
        """Load asset metadata from config/asset_registry.yaml.

        Returns a dict keyed by asset symbol with fields like name, asset_type,
        currency, issuer, and manager.
        """
        registry_path = PROJECT_ROOT / "config" / "asset_registry.yaml"
        meta: Dict[str, Dict[str, Any]] = {}
        if not registry_path.exists():
            return meta

        with open(registry_path, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}

        for entry in data.get("assets", []):
            symbol = entry.get("symbol")
            if symbol:
                meta[str(symbol)] = {
                    "name": entry.get("name"),
                    "asset_type": entry.get("asset_type"),
                    "currency": entry.get("currency"),
                    "issuer": entry.get("issuer"),
                    "manager": entry.get("manager"),
                }
        return meta

    def _load_product_registry(self) -> Dict[str, ProductDefinition]:
        """Build a minimal ProductDefinition registry from the asset registry.

        Maps each asset's asset_type string (e.g. cn_stock_sh, us_equity) to a
        ProductDefinition so the liquidity analyzer can consult product metadata.
        """
        registry_path = PROJECT_ROOT / "config" / "asset_registry.yaml"
        products: Dict[str, ProductDefinition] = {}
        if not registry_path.exists():
            return products

        with open(registry_path, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}

        for entry in data.get("assets", []):
            symbol = entry.get("symbol")
            if not symbol:
                continue
            asset_type = entry.get("asset_type", "")
            # Map common registry asset_type values to product_type names
            ptype = self._map_asset_type_to_product_type(asset_type)
            products[str(symbol)] = ProductDefinition(
                product_id=str(symbol),
                name=entry.get("name", str(symbol)),
                product_type=ptype,
                currency=entry.get("currency", "CNY"),
            )
        return products

    @staticmethod
    def _map_asset_type_to_product_type(asset_type: str) -> str:
        """Map an asset_type from the registry to a ProductDefinition product_type."""
        t = (asset_type or "").strip().lower()
        if not t:
            return "unknown"
        if t in ("cash", "currency", "deposit"):
            return "deposit"
        if "stock" in t or "equity" in t:
            return "equity"
        if "bond" in t and "fund" not in t:
            return "bond"
        if "fund" in t or "etf" in t:
            if "money" in t or "货币" in t:
                return "money_fund"
            if "bond" in t:
                return "bond_fund"
            if "mixed" in t:
                return "mixed_fund"
            return "index_fund"
        if "bank" in t or "wmp" in t:
            return "bank_wmp"
        if "structured" in t:
            return "structured_deposit"
        return "unknown"

    def _load_portfolio(self) -> None:
        if not self.config_path.exists():
            self._holdings = {}
            self._cash = {}
            return

        with open(self.config_path, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}

        self._cash = {str(k): float(v) for k, v in data.get("cash", {}).items()}
        self._holdings = {}
        for symbol, shares in data.get("positions", {}).items():
            self._holdings[str(symbol)] = float(shares)

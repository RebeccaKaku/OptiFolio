"""Application service for market data, optimization, and research backtests."""

from __future__ import annotations

from typing import Any, Dict, Optional, Sequence

import pandas as pd

from src.data_foundation import MarketDataRepository
from src.research import BacktestEngine, BacktestRequest

from .response import failure, success


class ResearchService:
    def __init__(
        self,
        market_data: Optional[MarketDataRepository] = None,
        backtest_engine: Optional[BacktestEngine] = None,
    ) -> None:
        self.market_data = market_data or MarketDataRepository()
        self.backtest_engine = backtest_engine or BacktestEngine()

    def list_market_assets(self) -> Dict[str, Any]:
        try:
            return success({"assets": self.market_data.list_assets()}, "Market assets loaded")
        except Exception as exc:
            return failure(str(exc), "MARKET_ASSET_LIST_ERROR")

    def get_prices(
        self,
        assets: Sequence[str],
        start: Optional[str] = None,
        end: Optional[str] = None,
        field: str = "adj_close",
    ) -> Dict[str, Any]:
        try:
            prices = self.market_data.get_prices(assets, start=start, end=end, fields=(field,))
            return success(self._frame_payload(prices), "Prices loaded")
        except Exception as exc:
            return failure(str(exc), "PRICE_MATRIX_ERROR", {"assets": list(assets)})

    def get_returns(
        self,
        assets: Sequence[str],
        start: Optional[str] = None,
        end: Optional[str] = None,
        frequency: str = "D",
    ) -> Dict[str, Any]:
        try:
            returns = self.market_data.get_returns(assets, start=start, end=end, frequency=frequency)
            return success(self._frame_payload(returns), "Returns loaded")
        except Exception as exc:
            return failure(str(exc), "RETURN_MATRIX_ERROR", {"assets": list(assets)})

    def get_missing_report(
        self,
        assets: Sequence[str],
        start: Optional[str] = None,
        end: Optional[str] = None,
    ) -> Dict[str, Any]:
        try:
            report = self.market_data.missing_report(assets, start=start, end=end)
            return success({"records": report.to_dict(orient="records")}, "Missing data report loaded")
        except Exception as exc:
            return failure(str(exc), "MISSING_REPORT_ERROR", {"assets": list(assets)})

    def run_backtest(
        self,
        assets: Sequence[str],
        target_weights: Optional[Dict[str, float]] = None,
        start: Optional[str] = None,
        end: Optional[str] = None,
        rebalance_frequency: str = "M",
        fee_rate: float = 0.0,
        initial_cash: float = 1.0,
        risk_free_rate: float = 0.0,
    ) -> Dict[str, Any]:
        try:
            prices = self.market_data.get_prices(assets, start=start, end=end)
            if prices.empty:
                return failure("No price data available for requested assets", "BACKTEST_NO_DATA")

            weights = target_weights or self._equal_weights(prices.columns)
            result = self.backtest_engine.run(
                BacktestRequest(
                    prices=prices,
                    target_weights=weights,
                    initial_cash=initial_cash,
                    rebalance_frequency=rebalance_frequency,
                    fee_rate=fee_rate,
                    risk_free_rate=risk_free_rate,
                )
            )
            return success(result.to_dict(), "Backtest completed")
        except Exception as exc:
            return failure(str(exc), "BACKTEST_ERROR", {"assets": list(assets)})

    def run_optimization(
        self,
        assets: Sequence[str],
        start: Optional[str] = None,
        end: Optional[str] = None,
        method: str = "mean_variance",
        objective: str = "max_sharpe",
        risk_free_rate: float = 0.02,
    ) -> Dict[str, Any]:
        try:
            from portfolio.optimizer import PortfolioOptimizer

            # 1. Validate method and objective values
            if method not in PortfolioOptimizer.VALID_METHODS:
                return failure(
                    f"Unknown method '{method}'. Valid methods: {PortfolioOptimizer.VALID_METHODS}",
                    "INVALID_OPTIMIZATION_METHOD",
                )

            if objective not in PortfolioOptimizer.VALID_OBJECTIVES:
                return failure(
                    f"Invalid objective '{objective}'. Supported objectives: {PortfolioOptimizer.VALID_OBJECTIVES}",
                    "INVALID_OPTIMIZATION_OBJECTIVE",
                )

            # 2. Fetch price data
            prices = self.market_data.get_prices(assets, start=start, end=end)

            # 3. Validate price data quality
            if prices.empty:
                return failure("No price data available for requested assets", "OPTIMIZATION_NO_DATA")

            missing_assets = [a for a in assets if a not in prices.columns or prices[a].isna().all()]
            if missing_assets:
                return failure(
                    f"Insufficient data for assets: {missing_assets}",
                    "OPTIMIZATION_INSUFFICIENT_ASSETS",
                    {"missing_assets": missing_assets},
                )

            if len(prices) < 2:
                return failure(
                    f"Insufficient price history for optimization (need at least 2 points, got {len(prices)})",
                    "OPTIMIZATION_INSUFFICIENT_HISTORY",
                )

            # 4. Execute optimization with error handling
            try:
                optimizer = PortfolioOptimizer(method=method, risk_free_rate=risk_free_rate)
                result = optimizer.run(prices, optimization_method=objective)
            except Exception as exc:
                return failure(f"Optimizer failed: {str(exc)}", "OPTIMIZER_EXECUTION_ERROR")

            return success(
                {
                    "weights": result.weights,
                    "expected_return": result.expected_return,
                    "volatility": result.volatility,
                    "sharpe_ratio": result.sharpe_ratio,
                    "method_used": result.method_used,
                    "metadata": result.metadata,
                },
                "Optimization completed",
            )
        except Exception as exc:
            return failure(str(exc), "OPTIMIZATION_ERROR", {"assets": list(assets)})

    def build_summary(self, result: Dict[str, Any]) -> Dict[str, Any]:
        if not result.get("success"):
            return result
        data = result.get("data") or {}
        metrics = data.get("metrics", {})
        return success(
            {
                "metrics": metrics,
                "engine": data.get("engine"),
                "asset_contribution": data.get("asset_contribution", {}),
            },
            "Research summary generated",
        )

    def _equal_weights(self, assets: Sequence[str]) -> Dict[str, float]:
        if not assets:
            return {}
        weight = 1.0 / len(assets)
        return {asset: weight for asset in assets}

    def _frame_payload(self, frame: pd.DataFrame) -> Dict[str, Any]:
        if frame.empty:
            return {"index": [], "columns": [], "records": []}

        output = frame.copy()
        output.index = pd.to_datetime(output.index)
        records = output.reset_index(names="date")
        records["date"] = records["date"].dt.strftime("%Y-%m-%d")
        return {
            "index": [index.strftime("%Y-%m-%d") for index in output.index],
            "columns": list(output.columns),
            "records": records.to_dict(orient="records"),
        }

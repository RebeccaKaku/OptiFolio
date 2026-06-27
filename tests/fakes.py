"""Small in-memory test doubles for remote market-data contracts."""

from __future__ import annotations

from typing import Sequence

import pandas as pd


class InMemoryMarketDataGateway:
    def __init__(self, _root=None) -> None:
        self._series: dict[str, pd.Series] = {}

    def save_canonical(self, frame: pd.DataFrame, asset_id: str, source: str = "test", **_kwargs):
        data = frame.copy()
        if "date" in data.columns:
            index = pd.to_datetime(data.pop("date"))
        elif "timestamp" in data.columns:
            index = pd.to_datetime(data.pop("timestamp"))
        else:
            index = pd.to_datetime(data.index)
        value_column = "adj_close" if "adj_close" in data.columns else "close"
        values = pd.to_numeric(data[value_column], errors="coerce")
        self._series[asset_id] = pd.Series(values.to_numpy(), index=index, name=asset_id).sort_index()
        return frame

    def get_prices(self, assets: Sequence[str], start: str | None = None,
                   end: str | None = None, fields: Sequence[str] = ("adj_close",)) -> pd.DataFrame:
        columns = []
        for asset in assets:
            series = self._series.get(asset)
            if series is None:
                columns.append(pd.Series(name=asset, dtype=float))
                continue
            selected = series
            if start:
                selected = selected[selected.index >= pd.Timestamp(start)]
            if end:
                selected = selected[selected.index <= pd.Timestamp(end)]
            columns.append(selected.rename(asset))
        return pd.concat(columns, axis=1).sort_index() if columns else pd.DataFrame()

    def get_returns(self, assets: Sequence[str], start: str | None = None,
                    end: str | None = None, frequency: str = "D") -> pd.DataFrame:
        prices = self.get_prices(assets, start=start, end=end)
        if frequency.upper() not in {"D", "1D"} and not prices.empty:
            prices = prices.resample(frequency).last()
        return prices.pct_change().dropna(how="all")

    def list_assets(self) -> list[str]:
        return sorted(self._series)

    def missing_report(self, assets: Sequence[str], start: str | None = None,
                       end: str | None = None) -> pd.DataFrame:
        prices = self.get_prices(assets, start=start, end=end)
        return pd.DataFrame({
            "asset_id": list(assets),
            "observations": [int(prices[a].count()) if a in prices else 0 for a in assets],
            "missing": [int(prices[a].isna().sum()) if a in prices else 0 for a in assets],
        })

    def prices(self, symbol: str, start: str | None = None, end: str | None = None,
               mode: str = "fast", asset_type: str | None = None):
        frame = self.get_prices([symbol], start=start, end=end)
        return None if frame.empty or frame[symbol].dropna().empty else frame[symbol].dropna()

    def fx_rate(self, from_currency: str, to_currency: str,
                date_str: str | None = None, mode: str = "fast") -> float:
        if from_currency == to_currency:
            return 1.0
        asset_id = f"fx.{from_currency.lower()}_{to_currency.lower()}.spot"
        frame = self.get_prices([asset_id], end=date_str)
        if frame.empty or frame[asset_id].dropna().empty:
            raise LookupError(asset_id)
        return float(frame[asset_id].dropna().iloc[-1])

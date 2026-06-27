"""HTTP client and protocol for the independent FinDataProvider service."""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Any, Protocol, Sequence, runtime_checkable

import httpx
import pandas as pd


class DataServiceError(RuntimeError):
    """Base class for remote market-data failures."""


class DataServiceConfigurationError(DataServiceError):
    pass


class DataServiceUnavailableError(DataServiceError):
    pass


class DataNotAvailableError(DataServiceError):
    pass


@runtime_checkable
class MarketDataGateway(Protocol):
    def get_prices(self, assets: Sequence[str], start: str | None = None,
                   end: str | None = None, fields: Sequence[str] = ("adj_close",)) -> pd.DataFrame: ...
    def get_returns(self, assets: Sequence[str], start: str | None = None,
                    end: str | None = None, frequency: str = "D") -> pd.DataFrame: ...
    def list_assets(self) -> list[str]: ...
    def missing_report(self, assets: Sequence[str], start: str | None = None,
                       end: str | None = None) -> pd.DataFrame: ...


class HttpMarketDataClient:
    """Synchronous, no-cache client for FinDataProvider v1.

    The client deliberately has no local market-data fallback. A transport
    outage becomes ``DataServiceUnavailableError`` and missing assets are
    explicitly registered for asynchronous ingestion.
    """

    def __init__(
        self,
        base_url: str | None = None,
        token: str | None = None,
        timeout: float = 20.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        file_config = self._load_local_config()
        self.base_url = (
            base_url
            or os.environ.get("FINDATA_BASE_URL")
            or file_config.get("base_url")
            or "http://127.0.0.1:8020"
        ).rstrip("/")
        self.token = token or os.environ.get("FINDATA_API_TOKEN") or file_config.get("api_token")
        self.timeout = timeout
        self._transport = transport
        self._ensured_assets: set[str] = set()
        self._ensure_lock = threading.Lock()

    @staticmethod
    def _load_local_config() -> dict[str, str]:
        path = Path(__file__).resolve().parents[2] / "local" / "findata_client.json"
        if not path.exists():
            return {}
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except (OSError, json.JSONDecodeError):
            return {}

    def _headers(self) -> dict[str, str]:
        if not self.token:
            raise DataServiceConfigurationError(
                "FINDATA_API_TOKEN is not configured; set it in the environment "
                "or local/findata_client.json"
            )
        return {"Authorization": f"Bearer {self.token}"}

    def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        try:
            with httpx.Client(
                base_url=self.base_url,
                headers=self._headers(),
                timeout=self.timeout,
                transport=self._transport,
            ) as client:
                response = client.request(method, path, **kwargs)
        except httpx.HTTPError as exc:
            raise DataServiceUnavailableError(
                f"FinDataProvider unavailable at {self.base_url}: {exc}"
            ) from exc

        if response.status_code == 404:
            detail = self._detail(response)
            raise DataNotAvailableError(detail.get("code", "NO_DATA"))
        if response.status_code >= 500:
            raise DataServiceUnavailableError(
                f"FinDataProvider returned HTTP {response.status_code}"
            )
        if response.status_code >= 400:
            raise DataServiceError(
                f"FinDataProvider request failed ({response.status_code}): {self._detail(response)}"
            )
        payload = response.json()
        return payload.get("data", payload)

    @staticmethod
    def _detail(response: httpx.Response) -> dict[str, Any]:
        try:
            payload = response.json()
        except ValueError:
            return {"message": response.text}
        detail = payload.get("detail", payload)
        return detail if isinstance(detail, dict) else {"message": str(detail)}

    @staticmethod
    def _matrix(records: list[dict[str, Any]]) -> pd.DataFrame:
        if not records:
            return pd.DataFrame()
        frame = pd.DataFrame(records)
        date_column = "date" if "date" in frame.columns else "index" if "index" in frame.columns else None
        if date_column:
            frame[date_column] = pd.to_datetime(frame[date_column])
            frame = frame.set_index(date_column)
            frame.index.name = "date"
        return frame.sort_index()

    def ensure_asset(self, asset_id: str, asset_type: str | None = None) -> dict[str, Any]:
        return self._request(
            "POST", "/v1/assets/ensure",
            json={"asset_id": asset_id, "asset_type": asset_type},
        )

    def _ensure_asset_once(self, asset_id: str, asset_type: str | None = None) -> None:
        with self._ensure_lock:
            if asset_id in self._ensured_assets:
                return
            self._ensured_assets.add(asset_id)
        try:
            self.ensure_asset(asset_id, asset_type)
        except Exception:
            with self._ensure_lock:
                self._ensured_assets.discard(asset_id)
            raise

    def get_prices(
        self, assets: Sequence[str], start: str | None = None,
        end: str | None = None, fields: Sequence[str] = ("adj_close",),
    ) -> pd.DataFrame:
        if not assets:
            return pd.DataFrame()
        if len(fields) != 1:
            raise ValueError("FinDataProvider v1 supports one price field per request")
        params: list[tuple[str, str]] = [("assets", asset) for asset in assets]
        if start:
            params.append(("start", start))
        if end:
            params.append(("end", end))
        params.append(("field", fields[0]))
        try:
            records = self._request("GET", "/v1/prices", params=params)
        except DataNotAvailableError:
            for asset in assets:
                self._ensure_asset_once(asset)
            return pd.DataFrame()
        frame = self._matrix(records)
        for asset in assets:
            if asset not in frame.columns or frame[asset].dropna().empty:
                self._ensure_asset_once(asset)
        return frame

    def prices(self, symbol: str, start: str | None = None, end: str | None = None,
               mode: str = "fast", asset_type: str | None = None) -> pd.Series | None:
        frame = self.get_prices([symbol], start=start, end=end)
        if frame.empty:
            if asset_type:
                self._ensure_asset_once(symbol, asset_type)
            return None
        column = frame.columns[0]
        return frame[column].dropna().rename(symbol)

    def panel(self, symbols: Sequence[str], start: str | None = None,
              end: str | None = None, mode: str = "fast",
              asset_type: str | None = None) -> pd.DataFrame:
        return self.get_prices(symbols, start=start, end=end)

    def get_returns(self, assets: Sequence[str], start: str | None = None,
                    end: str | None = None, frequency: str = "D") -> pd.DataFrame:
        params: list[tuple[str, str]] = [("assets", asset) for asset in assets]
        if start:
            params.append(("start", start))
        if end:
            params.append(("end", end))
        records = self._request("GET", "/v1/returns", params=params)
        frame = self._matrix(records)
        if frequency.upper() not in {"D", "1D"} and not frame.empty:
            frame = frame.resample(frequency).apply(lambda values: (1.0 + values).prod() - 1.0)
        return frame

    def returns(self, symbol: str, start: str | None = None,
                end: str | None = None, frequency: str = "D",
                asset_type: str | None = None) -> pd.Series:
        frame = self.get_returns([symbol], start=start, end=end, frequency=frequency)
        return pd.Series(dtype=float) if frame.empty else frame.iloc[:, 0].rename(symbol)

    def list_assets(self) -> list[str]:
        rows = self._request("GET", "/v1/assets")
        return [str(row["asset_id"]) for row in rows]

    def missing_report(self, assets: Sequence[str], start: str | None = None,
                       end: str | None = None) -> pd.DataFrame:
        params: list[tuple[str, str]] = [("assets", asset) for asset in assets]
        if start:
            params.append(("start", start))
        if end:
            params.append(("end", end))
        return pd.DataFrame(self._request("GET", "/v1/quality/missing-report", params=params))

    def fx_rate(self, from_currency: str, to_currency: str,
                date_str: str | None = None, mode: str = "fast") -> float:
        from_currency = (from_currency or "").strip().upper()
        to_currency = (to_currency or "").strip().upper()
        if not (
            len(from_currency) == 3
            and from_currency.isalpha()
            and len(to_currency) == 3
            and to_currency.isalpha()
        ):
            raise DataNotAvailableError("INVALID_CURRENCY")
        if from_currency == to_currency:
            return 1.0
        params = {"from_currency": from_currency, "to_currency": to_currency}
        if date_str:
            params["date"] = date_str
        data = self._request("GET", "/v1/fx/rate", params=params)
        return float(data["rate"])

    def get_metadata(self, symbol: str, asset_type: str | None = None) -> dict[str, Any] | None:
        params = {"asset_type": asset_type} if asset_type else None
        try:
            return self._request("GET", f"/v1/assets/{symbol}/metadata", params=params)
        except DataNotAvailableError:
            self._ensure_asset_once(symbol, asset_type)
            return None

    def fund_fees(self, fund_code: str) -> dict[str, Any]:
        return self._request("GET", f"/v1/funds/{fund_code}/fees")

    def fund_status(self, fund_code: str) -> dict[str, Any]:
        return self._request("GET", f"/v1/funds/{fund_code}/status")

    def dividends(self, report_year: int = 2025) -> list[dict[str, Any]]:
        return self._request("GET", "/v1/dividends", params={"report_year": report_year})

    def observations(self, series_ids: Sequence[str], start: str | None = None,
                     end: str | None = None, known_at: str | None = None) -> pd.DataFrame:
        params: list[tuple[str, str]] = [("series_ids", series_id) for series_id in series_ids]
        for key, value in (("start", start), ("end", end), ("known_at", known_at)):
            if value:
                params.append((key, value))
        return pd.DataFrame(self._request("GET", "/v1/observations", params=params))

    def latest_observation(self, series_id: str, as_of: str | None = None,
                           known_at: str | None = None) -> dict[str, Any] | None:
        params = {"series_id": series_id}
        if as_of:
            params["as_of"] = as_of
        if known_at:
            params["known_at"] = known_at
        try:
            return self._request("GET", "/v1/observations/latest", params=params)
        except DataNotAvailableError:
            return None

    def observation_coverage(self, series_ids: Sequence[str] | None = None,
                             expected_stale_days: int | None = None) -> pd.DataFrame:
        params: list[tuple[str, str]] = []
        for series_id in series_ids or []:
            params.append(("series_ids", series_id))
        if expected_stale_days is not None:
            params.append(("stale_days", str(expected_stale_days)))
        return pd.DataFrame(self._request("GET", "/v1/observations/coverage", params=params))

    def ingestion_runs(self, limit: int = 100) -> list[dict[str, Any]]:
        return self._request("GET", "/v1/ingestion/runs", params={"limit": limit})

    def quality_reports(self, asset_id: str | None = None) -> list[dict[str, Any]]:
        params = {"asset_id": asset_id} if asset_id else None
        return self._request("GET", "/v1/quality/issues", params=params)

    def stale_price_check(self, n_days: int = 3) -> dict[str, Any]:
        return self._request("POST", "/v1/quality/stale", params={"n_days": n_days})

    def warmup(self, symbols: Sequence[str]) -> None:
        for symbol in symbols:
            self.prices(symbol)

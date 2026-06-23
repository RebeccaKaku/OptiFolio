"""On-demand rate fetcher and synchronizer for canonical observations.

This module contains the logic formerly in ``tools/sync_macro_rates.py``,
exposed as a library so ``findata.serving.DataProvider`` can populate missing
rate series on demand (``mode="live"``) without hardcoded fallbacks.
"""

from __future__ import annotations

import io
import logging
import time
from dataclasses import dataclass
from typing import Callable, Iterable
from urllib.request import urlopen

import pandas as pd

from findata.store import MarketDataRepository
from optifolio_contracts.identifiers import normalize_instrument_id

_log = logging.getLogger(__name__)

SOURCE_INTERBANK = "akshare-eastmoney-rate_interbank"
SOURCE_POLICY = "akshare-jin10-policy_rate"
SOURCE_FRED = "fred"


@dataclass(frozen=True)
class InterbankSpec:
    series_id: str
    market: str
    symbol: str
    indicator: str
    currency: str

    @property
    def group(self) -> str:
        return "interbank"

    @property
    def source(self) -> str:
        return SOURCE_INTERBANK

    @property
    def description(self) -> str:
        return f"{self.symbol} {self.indicator}"


@dataclass(frozen=True)
class PolicyRateSpec:
    series_id: str
    akshare_func: str
    currency: str
    country: str

    @property
    def group(self) -> str:
        return "policy"

    @property
    def source(self) -> str:
        return SOURCE_POLICY

    @property
    def description(self) -> str:
        return f"{self.country} policy rate"


@dataclass(frozen=True)
class FredRateSpec:
    series_id: str
    fred_id: str
    currency: str
    description: str

    @property
    def group(self) -> str:
        return "replacements"

    @property
    def source(self) -> str:
        return f"{SOURCE_FRED}:{self.fred_id}"

    @property
    def source_url(self) -> str:
        return f"https://fred.stlouisfed.org/series/{self.fred_id}"


INTERBANK_SPECS: tuple[InterbankSpec, ...] = (
    InterbankSpec("RATE_SHIBOR_CNY_ON", "上海银行同业拆借市场", "Shibor人民币", "隔夜", "CNY"),
    InterbankSpec("RATE_SHIBOR_CNY_1W", "上海银行同业拆借市场", "Shibor人民币", "1周", "CNY"),
    InterbankSpec("RATE_SHIBOR_CNY_1M", "上海银行同业拆借市场", "Shibor人民币", "1月", "CNY"),
    InterbankSpec("RATE_SHIBOR_CNY_3M", "上海银行同业拆借市场", "Shibor人民币", "3月", "CNY"),
    InterbankSpec("RATE_SHIBOR_CNY_6M", "上海银行同业拆借市场", "Shibor人民币", "6月", "CNY"),
    InterbankSpec("RATE_SHIBOR_CNY_1Y", "上海银行同业拆借市场", "Shibor人民币", "1年", "CNY"),
    InterbankSpec("RATE_LIBOR_USD_ON", "伦敦银行同业拆借市场", "Libor美元", "隔夜", "USD"),
    InterbankSpec("RATE_LIBOR_USD_1M", "伦敦银行同业拆借市场", "Libor美元", "1月", "USD"),
    InterbankSpec("RATE_LIBOR_USD_3M", "伦敦银行同业拆借市场", "Libor美元", "3月", "USD"),
    InterbankSpec("RATE_LIBOR_EUR_3M", "伦敦银行同业拆借市场", "Libor欧元", "3月", "EUR"),
    InterbankSpec("RATE_EURIBOR_EUR_3M", "欧洲银行同业拆借市场", "Euribor欧元", "3月", "EUR"),
    InterbankSpec("RATE_HIBOR_HKD_3M", "香港银行同业拆借市场", "Hibor港币", "3月", "HKD"),
    InterbankSpec("RATE_HIBOR_USD_3M", "香港银行同业拆借市场", "Hibor美元", "3月", "USD"),
)


POLICY_RATE_SPECS: tuple[PolicyRateSpec, ...] = (
    PolicyRateSpec("RATE_POLICY_CN", "macro_bank_china_interest_rate", "CNY", "CN"),
    PolicyRateSpec("RATE_POLICY_US", "macro_bank_usa_interest_rate", "USD", "US"),
    PolicyRateSpec("RATE_POLICY_EU", "macro_bank_euro_interest_rate", "EUR", "EU"),
    PolicyRateSpec("RATE_POLICY_UK", "macro_bank_english_interest_rate", "GBP", "UK"),
    PolicyRateSpec("RATE_POLICY_JP", "macro_bank_japan_interest_rate", "JPY", "JP"),
)


FRED_REPLACEMENT_SPECS: tuple[FredRateSpec, ...] = (
    FredRateSpec("RATE_SOFR_USD_ON", "SOFR", "USD", "Secured Overnight Financing Rate"),
    FredRateSpec("RATE_SONIA_GBP_ON", "IUDSOIA", "GBP", "Sterling Overnight Index Average"),
    FredRateSpec("RATE_ESTR_EUR_ON", "ECBESTRVOLWGTTRMDMNRT", "EUR", "Euro short-term rate"),
)


ALL_SPECS: tuple[InterbankSpec | PolicyRateSpec | FredRateSpec, ...] = (
    *INTERBANK_SPECS,
    *POLICY_RATE_SPECS,
    *FRED_REPLACEMENT_SPECS,
)

_SPEC_BY_ID: dict[str, InterbankSpec | PolicyRateSpec | FredRateSpec] = {
    spec.series_id: spec for spec in ALL_SPECS
}


def _canonical_series_id(spec: InterbankSpec | PolicyRateSpec | FredRateSpec) -> str:
    """Return the canonical observation series ID for a spec."""
    return normalize_instrument_id(spec.series_id, asset_type="rate")


_SPEC_BY_ID_CANONICAL: dict[str, InterbankSpec | PolicyRateSpec | FredRateSpec] = {
    _canonical_series_id(spec): spec for spec in ALL_SPECS
}


def _parse_yyyymmdd(value: str | None) -> pd.Timestamp | None:
    if not value:
        return None
    return pd.to_datetime(value, format="%Y%m%d", errors="raise")


def _with_known_at_next_day(df: pd.DataFrame) -> pd.DataFrame:
    result = df.copy()
    result["known_at"] = pd.to_datetime(result["effective_date"]) + pd.Timedelta(days=1)
    return result


def normalize_interbank_frame(raw: pd.DataFrame, spec: InterbankSpec) -> pd.DataFrame:
    """Normalize AkShare rate_interbank output to canonical observations."""
    if raw is None or raw.empty:
        return pd.DataFrame()

    date_col = "报告日" if "报告日" in raw.columns else "日期"
    if date_col not in raw.columns or "利率" not in raw.columns:
        raise ValueError(f"Unexpected interbank columns for {spec.series_id}: {list(raw.columns)}")

    df = pd.DataFrame({
        "effective_date": pd.to_datetime(raw[date_col], errors="coerce"),
        "value": pd.to_numeric(raw["利率"], errors="coerce") / 100.0,
    })
    df = df.dropna(subset=["effective_date", "value"])
    df = df[df["value"] > 0]
    df = df.drop_duplicates(subset=["effective_date"], keep="last")
    df = _with_known_at_next_day(df)
    return df.sort_values("effective_date").reset_index(drop=True)


def normalize_policy_rate_frame(raw: pd.DataFrame, spec: PolicyRateSpec) -> pd.DataFrame:
    """Normalize AkShare central-bank decision output to observations."""
    if raw is None or raw.empty:
        return pd.DataFrame()

    if "日期" not in raw.columns or "今值" not in raw.columns:
        raise ValueError(f"Unexpected policy-rate columns for {spec.series_id}: {list(raw.columns)}")

    df = pd.DataFrame({
        "effective_date": pd.to_datetime(raw["日期"], errors="coerce"),
        "value": pd.to_numeric(raw["今值"], errors="coerce") / 100.0,
    })
    df = df.dropna(subset=["effective_date", "value"])
    df = df[df["value"] >= -0.05]
    df = df.drop_duplicates(subset=["effective_date"], keep="last")
    df = _with_known_at_next_day(df)
    return df.sort_values("effective_date").reset_index(drop=True)


def normalize_fred_rate_frame(raw: pd.DataFrame, spec: FredRateSpec) -> pd.DataFrame:
    """Normalize FRED percent-rate CSV output to canonical observations."""
    if raw is None or raw.empty:
        return pd.DataFrame()

    if "observation_date" in raw.columns:
        date_col = "observation_date"
    elif "DATE" in raw.columns:
        date_col = "DATE"
    else:
        raise ValueError(f"Unexpected FRED date columns for {spec.series_id}: {list(raw.columns)}")

    value_col = spec.fred_id if spec.fred_id in raw.columns else None
    if value_col is None:
        candidates = [c for c in raw.columns if c != date_col]
        if len(candidates) == 1:
            value_col = candidates[0]
        else:
            raise ValueError(f"Unexpected FRED value columns for {spec.series_id}: {list(raw.columns)}")

    df = pd.DataFrame({
        "effective_date": pd.to_datetime(raw[date_col], errors="coerce"),
        "value": pd.to_numeric(raw[value_col].replace(".", pd.NA), errors="coerce") / 100.0,
    })
    df = df.dropna(subset=["effective_date", "value"])
    df = df[df["value"] >= -0.05]
    df = df.drop_duplicates(subset=["effective_date"], keep="last")
    df = _with_known_at_next_day(df)
    return df.sort_values("effective_date").reset_index(drop=True)


def _filter_dates(df: pd.DataFrame, start: str | None, end: str | None) -> pd.DataFrame:
    if df.empty:
        return df
    start_ts = _parse_yyyymmdd(start)
    end_ts = _parse_yyyymmdd(end)
    mask = pd.Series(True, index=df.index)
    if start_ts is not None:
        mask &= pd.to_datetime(df["effective_date"]) >= start_ts
    if end_ts is not None:
        mask &= pd.to_datetime(df["effective_date"]) <= end_ts
    return df.loc[mask].reset_index(drop=True)


def fetch_interbank(spec: InterbankSpec, start: str | None, end: str | None) -> pd.DataFrame:
    import akshare as ak

    raw = ak.rate_interbank(
        market=spec.market,
        symbol=spec.symbol,
        indicator=spec.indicator,
    )
    return _filter_dates(normalize_interbank_frame(raw, spec), start, end)


def fetch_policy_rate(spec: PolicyRateSpec, start: str | None, end: str | None) -> pd.DataFrame:
    import akshare as ak

    func: Callable[[], pd.DataFrame] = getattr(ak, spec.akshare_func)
    raw = func()
    return _filter_dates(normalize_policy_rate_frame(raw, spec), start, end)


def fetch_fred_rate(spec: FredRateSpec, start: str | None, end: str | None) -> pd.DataFrame:
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={spec.fred_id}"
    last_error: Exception | None = None
    for attempt in range(2):
        try:
            with urlopen(url, timeout=25) as response:
                content = response.read().decode("utf-8")
            break
        except Exception as exc:
            last_error = exc
            if attempt < 1:
                time.sleep(2.0 * (attempt + 1))
    else:
        raise last_error or RuntimeError(f"Failed to fetch FRED series {spec.fred_id}")
    raw = pd.read_csv(io.StringIO(content))
    return _filter_dates(normalize_fred_rate_frame(raw, spec), start, end)


def macro_series_catalog() -> list[dict[str, str]]:
    """Return the known macro/rate series catalog for docs, APIs, and schedulers."""
    records: list[dict[str, str]] = []
    for spec in ALL_SPECS:
        record = {
            "series_id": _canonical_series_id(spec),
            "group": spec.group,
            "currency": spec.currency,
            "source": spec.source,
            "description": spec.description,
            "unit": "decimal",
        }
        if isinstance(spec, InterbankSpec):
            record.update({
                "market": spec.market,
                "symbol": spec.symbol,
                "indicator": spec.indicator,
            })
        elif isinstance(spec, PolicyRateSpec):
            record.update({
                "akshare_func": spec.akshare_func,
                "country": spec.country,
            })
        elif isinstance(spec, FredRateSpec):
            record.update({
                "fred_id": spec.fred_id,
                "source_url": spec.source_url,
            })
            if spec.series_id == "RATE_SONIA_GBP_ON":
                record["fallback_note"] = (
                    "Official BoE IADB series IUDSOIA; FRED mirror may time out "
                    "from this machine. Do not synthesize values."
                )
        records.append(record)
    return records


def sync_rate_series(
    series_id: str,
    repo: MarketDataRepository | None = None,
    *,
    start: str | None = None,
    end: str | None = None,
    dry_run: bool = False,
) -> tuple[int, str]:
    """Fetch and store one macro-rate series.

    Returns ``(row_count, source_label)``. Raises if the series is unknown or
    the fetch fails.
    """
    spec = _SPEC_BY_ID.get(series_id) or _SPEC_BY_ID_CANONICAL.get(series_id)
    if spec is None:
        # Allow canonical/old IDs to be passed interchangeably.
        try:
            canonical = normalize_instrument_id(series_id, asset_type="rate")
            spec = _SPEC_BY_ID_CANONICAL.get(canonical)
        except Exception:
            spec = None
    if spec is None:
        raise ValueError(f"Unknown rate series_id: {series_id}")

    if isinstance(spec, InterbankSpec):
        df = fetch_interbank(spec, start, end)
        source = SOURCE_INTERBANK
    elif isinstance(spec, PolicyRateSpec):
        df = fetch_policy_rate(spec, start, end)
        source = SOURCE_POLICY
    else:
        df = fetch_fred_rate(spec, start, end)
        source = f"{SOURCE_FRED}:{spec.fred_id}"

    if df.empty:
        return 0, source

    if dry_run:
        return len(df), source

    repo = repo or MarketDataRepository()
    canonical_id = _canonical_series_id(spec)
    repo.save_observations(
        df,
        series_id=canonical_id,
        source=source,
        unit="decimal",
        currency=spec.currency,
    )
    return len(df), source


def sync_rates(
    series_ids: Iterable[str] | None = None,
    groups: Iterable[str] | None = None,
    repo: MarketDataRepository | None = None,
    *,
    start: str | None = None,
    end: str | None = None,
    dry_run: bool = False,
) -> dict[str, tuple[int, str]]:
    """Fetch and store multiple macro-rate series.

    ``groups`` may contain ``interbank``, ``policy``, and/or ``replacements``.
    If ``series_ids`` is given, only those series are synced (they must exist
    in the selected groups).
    """
    group_set = {g.strip().lower() for g in groups if g and g.strip()} if groups else {"interbank", "policy", "replacements"}
    requested = {s.strip().upper() for s in series_ids if s and s.strip()} if series_ids else None

    specs: list[InterbankSpec | PolicyRateSpec | FredRateSpec] = []
    if "interbank" in group_set:
        specs.extend(INTERBANK_SPECS)
    if "policy" in group_set:
        specs.extend(POLICY_RATE_SPECS)
    if "replacements" in group_set:
        specs.extend(FRED_REPLACEMENT_SPECS)

    if requested:
        specs = [spec for spec in specs if spec.series_id in requested]

    results: dict[str, tuple[int, str]] = {}
    for spec in specs:
        try:
            rows, source = sync_rate_series(
                spec.series_id, repo=repo, start=start, end=end, dry_run=dry_run
            )
            results[spec.series_id] = (rows, source)
        except Exception as exc:
            _log.warning("Failed to sync %s: %s", spec.series_id, exc)
            results[spec.series_id] = (0, f"error:{exc}")
    return results

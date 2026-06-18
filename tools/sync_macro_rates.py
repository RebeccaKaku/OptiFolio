#!/usr/bin/env python
"""Sync interbank and policy-rate macro series into canonical observations.

Examples:
    python tools/sync_macro_rates.py --dry-run
    python tools/sync_macro_rates.py --series RATE_SHIBOR_CNY_3M,RATE_LIBOR_USD_3M
    python tools/sync_macro_rates.py --groups interbank,policy --start 20240101

All rates are stored as decimals, not percentage points:
    2.35% -> 0.0235
"""

from __future__ import annotations

import argparse
import io
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable
from urllib.request import urlopen

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.data_foundation.repository import MarketDataRepository


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


def macro_series_catalog() -> list[dict[str, str]]:
    """Return the known macro/rate series catalog for docs, APIs, and schedulers."""
    records: list[dict[str, str]] = []
    for spec in (*INTERBANK_SPECS, *POLICY_RATE_SPECS, *FRED_REPLACEMENT_SPECS):
        record = {
            "series_id": spec.series_id,
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


def _selected_specs(
    groups: set[str],
    requested: set[str] | None,
) -> list[InterbankSpec | PolicyRateSpec | FredRateSpec]:
    specs: list[InterbankSpec | PolicyRateSpec | FredRateSpec] = []
    if "interbank" in groups:
        specs.extend(INTERBANK_SPECS)
    if "policy" in groups:
        specs.extend(POLICY_RATE_SPECS)
    if "replacements" in groups:
        specs.extend(FRED_REPLACEMENT_SPECS)
    if requested is not None:
        specs = [spec for spec in specs if spec.series_id in requested]
    return specs


def select_specs(
    groups: Iterable[str],
    requested: Iterable[str] | None = None,
) -> list[InterbankSpec | PolicyRateSpec | FredRateSpec]:
    """Public helper for schedulers and tests."""
    group_set = {g.strip().lower() for g in groups if g and g.strip()}
    requested_set = {s.strip().upper() for s in requested if s and s.strip()} if requested else None
    return _selected_specs(group_set, requested_set)


def sync_specs(
    specs: Iterable[InterbankSpec | PolicyRateSpec | FredRateSpec],
    repo: MarketDataRepository,
    *,
    start: str | None,
    end: str | None,
    dry_run: bool,
) -> tuple[int, int]:
    ok_count = 0
    total_rows = 0

    for spec in specs:
        print(f"{spec.series_id}...", end=" ", flush=True)
        try:
            if isinstance(spec, InterbankSpec):
                df = fetch_interbank(spec, start, end)
                source = SOURCE_INTERBANK
            elif isinstance(spec, PolicyRateSpec):
                df = fetch_policy_rate(spec, start, end)
                source = SOURCE_POLICY
            else:
                df = fetch_fred_rate(spec, start, end)
                source = f"{SOURCE_FRED}:{spec.fred_id}"
        except Exception as exc:
            print(f"fetch error: {exc}")
            continue

        if df.empty:
            print("no data")
            continue

        if dry_run:
            print(
                f"would save {len(df)} rows "
                f"[{pd.Timestamp(df['effective_date'].min()).date()} .. "
                f"{pd.Timestamp(df['effective_date'].max()).date()}]"
            )
        else:
            repo.save_observations(
                df,
                series_id=spec.series_id,
                source=source,
                unit="decimal",
                currency=spec.currency,
            )
            print(
                f"saved {len(df)} rows "
                f"[{pd.Timestamp(df['effective_date'].min()).date()} .. "
                f"{pd.Timestamp(df['effective_date'].max()).date()}]"
            )

        ok_count += 1
        total_rows += len(df)

    return ok_count, total_rows


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Sync SHIBOR/LIBOR/EURIBOR/HIBOR, policy rates, and LIBOR replacement rates"
    )
    parser.add_argument(
        "--groups",
        default="interbank,policy,replacements",
        help="Comma-separated groups: interbank,policy,replacements. Default: all.",
    )
    parser.add_argument(
        "--series",
        help="Comma-separated series IDs to sync. Default: all selected groups.",
    )
    parser.add_argument("--start", help="Start date YYYYMMDD.")
    parser.add_argument("--end", help="End date YYYYMMDD.")
    parser.add_argument("--dry-run", action="store_true", help="Fetch and preview without saving.")
    args = parser.parse_args()

    groups = {g.strip().lower() for g in args.groups.split(",") if g.strip()}
    invalid_groups = groups - {"interbank", "policy", "replacements"}
    if invalid_groups:
        raise SystemExit(f"Unknown group(s): {sorted(invalid_groups)}")

    requested = {s.strip().upper() for s in args.series.split(",")} if args.series else None
    specs = select_specs(groups, requested)
    if requested:
        known = {spec.series_id for spec in _selected_specs({"interbank", "policy", "replacements"}, None)}
        missing = requested - known
        if missing:
            raise SystemExit(f"Unknown series ID(s): {sorted(missing)}")

    if not specs:
        raise SystemExit("No series selected")

    print(f"Sync macro rates: {len(specs)} series")
    if args.start or args.end:
        print(f"Date filter: {args.start or '-inf'} .. {args.end or '+inf'}")
    if args.dry_run:
        print("[DRY RUN — no data will be saved]")

    ok_count, total_rows = sync_specs(
        specs,
        MarketDataRepository(),
        start=args.start,
        end=args.end,
        dry_run=args.dry_run,
    )
    print(f"Done: {ok_count}/{len(specs)} series, {total_rows} rows")


if __name__ == "__main__":
    main()

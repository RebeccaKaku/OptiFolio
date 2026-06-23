"""Canonical financial identifier definitions and normalization helpers.

All identifiers are lowercase and dot-separated. Examples:

    equity.us.aapl
    equity.cn.sh.600519
    equity.cn.sz.000001
    fund.cn.money.000198
    fund.cn.mixed.005827
    fund.cn.etf.sh.510300
    fund.cn.bond.xxxxxx
    fund.cn.stock.xxxxxx
    wmp.cn.icbc.23gs8125
    wmp.cn.boc.amhqlxttusd01b
    wmp.cn.bosc.wpxk24m1203a
    fx.usd_cny.spot
    rate.cn.shibor.1y
    rate.us.sofr.on

The module is intentionally dependency-free so that it can live in
``optifolio_contracts``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Tuple


class InvalidInstrumentIdError(ValueError):
    """Raised when an instrument ID cannot be parsed or normalized."""


class AmbiguousInstrumentIdError(InvalidInstrumentIdError):
    """Raised when a raw symbol maps to more than one canonical instrument."""


#: Regex for a 6-digit Chinese security code.
_CN_CODE_RE = re.compile(r"^\d{6}$")

#: Regex for CN stock prefixes.
_CN_PREFIX_RE = re.compile(r"^(sh|sz|bj)(\d{6})$", re.IGNORECASE)

#: Regex for a 6-character FX pair (e.g. USDCNY).
_FX_PAIR_RE = re.compile(r"^([a-zA-Z]{3})[_/\-]?([a-zA-Z]{3})$")

#: Regex for old-style rate series IDs like RATE_SHIBOR_CNY_1Y.
_OLD_RATE_RE = re.compile(r"^RATE_([A-Z0-9_]+)_[A-Z]{3}_[A-Z0-9]+$")


def _infer_cn_exchange(code: str) -> str:
    """Infer Shanghai/Shenzhen/Beijing exchange from a 6-digit code.

    Raises InvalidInstrumentIdError if the code range is unrecognized.
    """
    if not _CN_CODE_RE.match(code):
        raise InvalidInstrumentIdError(f"Not a 6-digit CN code: {code!r}")

    # Shanghai main board / STAR
    if code.startswith(("600", "601", "603", "605", "688")):
        return "sh"
    # Shenzhen main / SME / ChiNext
    if code.startswith(("000", "001", "002", "003", "300", "301")):
        return "sz"
    # Beijing
    if code.startswith(("430", "83", "87", "88", "89")):
        return "bj"

    raise InvalidInstrumentIdError(
        f"Cannot infer exchange for CN code {code!r}"
    )


_FUND_ASSET_TYPES = frozenset({
    "cn_fund", "cn_fund_open", "cn_fund_money", "cn_money_market_fund",
    "cn_fund_mixed", "cn_fund_bond", "cn_fund_stock", "cn_fund_index",
    "cn_fund_qdii", "cn_fund_etf", "cn_fund_lof", "cn_fund_fof",
})


def _is_fund_asset_type(asset_type: str) -> bool:
    """Return True if *asset_type* represents a fund."""
    return asset_type.lower() in _FUND_ASSET_TYPES or asset_type.startswith("cn_fund")


def _fund_subtype(asset_type: str = "", fund_type_raw: str = "") -> str:
    """Map akshare fund type or asset_type to a fund subtype segment.

    ``fund_type_raw`` (from akshare ``基金类型`` field) takes priority.
    Examples: 货币型-普通货币 → money, 混合型-偏股 → mixed, 指数型-股票 → index.
    """
    ft = fund_type_raw.strip()
    if ft:
        ft_lower = ft.lower()
        if ft.startswith("货币") or "货币" in ft:
            return "money"
        if ft.startswith("混合") or "混合" in ft:
            return "mixed"
        if ft.startswith("债券") or "债券" in ft:
            return "bond"
        if ft.startswith("股票") or "股票" in ft:
            return "stock"
        if ft.startswith("指数") or "指数" in ft:
            return "index"
        if ft_lower.startswith("qdii"):
            return "qdii"
        if ft_lower.startswith("fof"):
            return "fof"
    # Fallback: map from asset_type
    subtype_map = {
        "cn_fund_money": "money",
        "cn_money_market_fund": "money",
        "cn_fund_mixed": "mixed",
        "cn_fund_bond": "bond",
        "cn_fund_stock": "stock",
        "cn_fund_index": "index",
        "cn_fund_qdii": "qdii",
        "cn_fund_etf": "etf",
    }
    at = asset_type.lower()
    if at in subtype_map:
        return subtype_map[at]
    if at.startswith("cn_fund"):
        return "mixed"  # safest default for CN mutual funds
    raise InvalidInstrumentIdError(f"Cannot determine fund subtype from asset_type={asset_type!r} fund_type_raw={fund_type_raw!r}")


def _classify_wmp(code: str) -> str:
    """Classify a wealth-management product code by bank.

    The regexes mirror ``findata.adapters.bank_wmp``.
    """
    lowered = code.lower()
    if re.match(r"^\d{2}[a-z0-9]{6}$", lowered):
        return "icbc"
    if re.match(r"^[a-z]{5,}[a-z0-9]{5,}$", lowered):
        return "boc"
    if re.match(r"^[a-z]{1,6}\d+[a-z0-9]*$", lowered):
        return "bosc"
    raise InvalidInstrumentIdError(
        f"Cannot classify WMP code {code!r}; expected ICBC/BOC/BOSC pattern"
    )


def _normalize_fx(raw: str) -> str:
    """Normalize FX pair representations to fx.base_quote.spot."""
    if raw.lower().startswith("fx."):
        parts = raw.lower().split(".")
        if len(parts) == 3 and parts[2] == "spot" and _FX_PAIR_RE.match(parts[1]):
            return raw.lower()
        raise InvalidInstrumentIdError(f"Malformed FX canonical ID: {raw!r}")

    m = _FX_PAIR_RE.match(raw)
    if not m:
        raise InvalidInstrumentIdError(f"Unrecognized FX pair format: {raw!r}")
    base, quote = m.group(1).lower(), m.group(2).lower()
    return f"fx.{base}_{quote}.spot"


def _normalize_rate(raw: str) -> str:
    """Normalize old RATE_* series IDs or shorthand rate symbols."""
    lowered = raw.lower()
    if lowered.startswith("rate."):
        # Already canonical; do minimal validation.
        if len(lowered.split(".")) < 3:
            raise InvalidInstrumentIdError(f"Malformed rate ID: {raw!r}")
        return lowered

    # Old-style policy IDs: RATE_POLICY_CN -> rate.cn.policy
    policy_match = re.match(r"^RATE_POLICY_(CN|US|EU|UK|JP|HK|GBP|EUR|USD|CNY)$", raw.upper())
    if policy_match:
        return f"rate.{policy_match.group(1).lower()}.policy"

    # Old-style RATE_SHIBOR_CNY_1Y -> rate.cn.shibor.1y
    m = re.match(r"^RATE_([A-Z]+)_(CN|US|EU|UK|JP|HK|HKD|GBP|EUR|USD|CNY)_(ON|1W|1M|3M|6M|1Y|POLICY)$", raw.upper())
    if m:
        index, country, tenor = m.group(1).lower(), m.group(2).lower(), m.group(3).lower()
        # Country may already be embedded in index names like "shibor".
        if index in ("shibor",):
            return f"rate.cn.{index}.{tenor}"
        if index in ("sofr",):
            return f"rate.us.{index}.{tenor}"
        if index in ("sonia",):
            return f"rate.uk.{index}.{tenor}"
        if index in ("estr",):
            return f"rate.eu.{index}.{tenor}"
        if index in ("euribor",):
            return f"rate.eu.{index}.{tenor}"
        if index in ("libor",):
            return f"rate.uk.{index}.{tenor}"
        if index in ("hibor",):
            return f"rate.hk.{index}.{tenor}"
        if index == "policy":
            return f"rate.{country}.policy"

    raise InvalidInstrumentIdError(f"Unrecognized rate identifier: {raw!r}")


@dataclass(frozen=True)
class InstrumentIdParts:
    """Parsed components of a canonical instrument ID."""

    canonical: str
    segments: Tuple[str, ...]

    @property
    def asset_class(self) -> str:
        return self.segments[0] if self.segments else ""

    @property
    def market(self) -> str | None:
        return self.segments[1] if len(self.segments) > 1 else None

    @property
    def code(self) -> str:
        """Return the final code/token portion."""
        return self.segments[-1] if self.segments else ""


def validate_instrument_id(canonical: str) -> None:
    """Validate a canonical instrument ID. Raises on invalid."""
    if not canonical:
        raise InvalidInstrumentIdError("Instrument ID cannot be empty")

    if canonical != canonical.lower():
        raise InvalidInstrumentIdError(
            f"Instrument ID must be lowercase: {canonical!r}"
        )

    segments = canonical.split(".")
    if len(segments) < 2:
        raise InvalidInstrumentIdError(
            f"Instrument ID needs at least 2 segments: {canonical!r}"
        )

    asset_class = segments[0]
    if asset_class == "equity":
        if len(segments) not in (3, 4):
            raise InvalidInstrumentIdError(
                f"equity ID must have 3 or 4 segments: {canonical!r}"
            )
        market = segments[1]
        if market == "us":
            if len(segments) != 3 or not segments[2]:
                raise InvalidInstrumentIdError(
                    f"US equity ID must be equity.us.<ticker>: {canonical!r}"
                )
        elif market == "cn":
            if len(segments) != 4 or segments[2] not in ("sh", "sz", "bj"):
                raise InvalidInstrumentIdError(
                    f"CN equity ID must be equity.cn.<sh|sz|bj>.<code>: {canonical!r}"
                )
            if not _CN_CODE_RE.match(segments[3]):
                raise InvalidInstrumentIdError(
                    f"CN equity code must be 6 digits: {canonical!r}"
                )
        else:
            raise InvalidInstrumentIdError(
                f"Unsupported equity market: {market!r} in {canonical!r}"
            )

    elif asset_class == "fund":
        if segments[1] != "cn":
            raise InvalidInstrumentIdError(
                f"Only CN funds supported currently: {canonical!r}"
            )
        # fund.cn.etf.<sh|sz>.<code>  (5 segments — ETF with exchange)
        if len(segments) == 5:
            if segments[2] != "etf" or segments[3] not in ("sh", "sz"):
                raise InvalidInstrumentIdError(
                    f"ETF fund ID must be fund.cn.etf.<sh|sz>.<code>: {canonical!r}"
                )
            if not _CN_CODE_RE.match(segments[4]):
                raise InvalidInstrumentIdError(
                    f"CN ETF code must be 6 digits: {canonical!r}"
                )
        # fund.cn.<subtype>.<code>  (4 segments)
        elif len(segments) == 4:
            if segments[2] not in ("open", "money", "mixed", "bond", "stock", "index", "qdii"):
                raise InvalidInstrumentIdError(
                    f"Unknown fund subtype {segments[2]!r} in {canonical!r}"
                )
            if not _CN_CODE_RE.match(segments[3]):
                raise InvalidInstrumentIdError(
                    f"CN fund code must be 6 digits: {canonical!r}"
                )
        # fund.cn.<code>  (3 segments — legacy, bare code)
        elif len(segments) == 3:
            if not _CN_CODE_RE.match(segments[2]):
                raise InvalidInstrumentIdError(
                    f"CN fund code must be 6 digits: {canonical!r}"
                )
        else:
            raise InvalidInstrumentIdError(
                f"fund ID must have 3, 4, or 5 segments: {canonical!r}"
            )

    elif asset_class == "wmp":
        if len(segments) != 4 or segments[1] != "cn":
            raise InvalidInstrumentIdError(
                f"WMP ID must be wmp.cn.<bank>.<code>: {canonical!r}"
            )
        if segments[2] not in ("icbc", "boc", "bosc"):
            raise InvalidInstrumentIdError(
                f"Unsupported WMP bank: {segments[2]!r} in {canonical!r}"
            )

    elif asset_class == "fx":
        if len(segments) != 3 or segments[2] != "spot":
            raise InvalidInstrumentIdError(
                f"FX ID must be fx.<base>_<quote>.spot: {canonical!r}"
            )
        if not _FX_PAIR_RE.match(segments[1].replace("_", "")):
            raise InvalidInstrumentIdError(
                f"Malformed FX pair in ID: {canonical!r}"
            )

    elif asset_class == "rate":
        if len(segments) < 3:
            raise InvalidInstrumentIdError(
                f"Rate ID must have at least 3 segments: {canonical!r}"
            )

    else:
        raise InvalidInstrumentIdError(
            f"Unknown asset class {asset_class!r} in {canonical!r}"
        )


def parse_instrument_id(canonical: str) -> InstrumentIdParts:
    """Parse and validate a canonical instrument ID."""
    validate_instrument_id(canonical)
    return InstrumentIdParts(canonical=canonical, segments=tuple(canonical.split(".")))


def normalize_instrument_id(
    raw: str,
    *,
    asset_type: str | None = None,
    fund_type_raw: str = "",
) -> str:
    """Convert a raw symbol or display ID to a canonical instrument ID.

    Args:
        raw: Raw symbol such as ``AAPL``, ``sh600519``, ``USDCNY``,
             ``23GS8125``, or an already-canonical ID.
        asset_type: Optional hint from the adapter/registry, e.g.
                    ``cn_stock``, ``cn_fund``, ``bank_wmp``.
        fund_type_raw: Optional akshare ``基金类型`` value for fund subtype
                       resolution (e.g. ``货币型-普通货币`` → ``money``).

    Raises:
        InvalidInstrumentIdError: If the input cannot be normalized.
        AmbiguousInstrumentIdError: If a bare 6-digit CN code is provided
            without enough context to decide stock vs fund.
    """
    if not raw or not isinstance(raw, str):
        raise InvalidInstrumentIdError(f"Invalid instrument input: {raw!r}")

    stripped = raw.strip()
    lowered = stripped.lower()

    # Already canonical
    try:
        validate_instrument_id(lowered)
        return lowered
    except InvalidInstrumentIdError:
        pass

    # FX pair
    try:
        return _normalize_fx(stripped)
    except InvalidInstrumentIdError:
        pass

    # Rate series
    try:
        return _normalize_rate(stripped)
    except InvalidInstrumentIdError:
        pass

    # CN prefixed stock
    m = _CN_PREFIX_RE.match(stripped)
    if m:
        exchange, code = m.group(1).lower(), m.group(2)
        return f"equity.cn.{exchange}.{code}"

    # CN 6-digit code: need context
    if _CN_CODE_RE.match(stripped):
        if asset_type and _is_fund_asset_type(asset_type):
            subtype = _fund_subtype(asset_type, fund_type_raw)
            return f"fund.cn.{subtype}.{stripped}"
        if asset_type and asset_type.startswith("cn_stock"):
            exchange = _infer_cn_exchange(stripped)
            return f"equity.cn.{exchange}.{stripped}"
        # Without context, 000001-style codes are ambiguous.
        raise AmbiguousInstrumentIdError(
            f"Bare 6-digit CN code {stripped!r} is ambiguous; "
            "provide asset_type or use prefixed form like sh600519"
        )

    # US equity / generic ticker
    if re.match(r"^[a-zA-Z]{1,5}$", stripped):
        return f"equity.us.{lowered}"

    # WMP product codes
    if asset_type and asset_type.startswith("bank_wmp"):
        bank = _classify_wmp(stripped)
        return f"wmp.cn.{bank}.{lowered}"
    try:
        bank = _classify_wmp(stripped)
        return f"wmp.cn.{bank}.{lowered}"
    except InvalidInstrumentIdError:
        pass

    raise InvalidInstrumentIdError(
        f"Unable to normalize instrument identifier: {raw!r}"
    )

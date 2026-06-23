"""Canonical dataset identifiers.

Dataset IDs follow the convention ``<domain>.<dataset>.<frequency_or_shape>``.
They are source-independent and map to one or more adapters internally.
"""

from __future__ import annotations

RATES_SHIBOR_DAILY: str = "rates.shibor.daily"
RATES_SOFR_DAILY: str = "rates.sofr.daily"
RATES_POLICY_EVENT: str = "rates.policy.event"

FX_SPOT_DAILY: str = "fx.spot.daily"

FUNDS_NAV_DAILY: str = "funds.nav.daily"

EQUITIES_OHLCV_DAILY: str = "equities.ohlcv.daily"

WMP_NAV_IRREGULAR: str = "wmp.nav.irregular"

MACRO_CPI_MONTHLY: str = "macro.cpi.monthly"

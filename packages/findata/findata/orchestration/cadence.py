"""Update cadence rules per asset type.

Each asset type has a refresh schedule: how often to fetch, the earliest
UTC time to trigger a refresh, and the maximum tolerated staleness.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timezone


@dataclass(frozen=True)
class UpdateCadence:
    """Refresh schedule for one asset type.

    Attributes:
        asset_type: Identifier matching fetcher registry keys.
        frequency: Human-readable label (``"daily"``, ``"hourly"``,
            ``"t+1_morning"``).
        trigger_after_utc: Earliest UTC wall-clock time to consider a
            refresh *due*.  For daily assets this is typically after
            market close.
        max_stale_hours: If the last update is older than this many hours,
            a refresh is forced regardless of ``trigger_after_utc``.
    """

    asset_type: str
    frequency: str
    trigger_after_utc: time
    max_stale_hours: int


CADENCE_TABLE: dict[str, UpdateCadence] = {
    "us_equity": UpdateCadence("us_equity", "daily", time(21, 30), 28),
    "cn_stock":  UpdateCadence("cn_stock",  "daily", time(7, 30),  28),
    "cn_fund":   UpdateCadence("cn_fund",   "t+1_morning", time(1, 0), 36),
    "forex":     UpdateCadence("forex",     "hourly", time(0, 0),  4),
    "bank_wmp":  UpdateCadence("bank_wmp",  "daily", time(12, 0),  28),
    "bank_wm_boc": UpdateCadence("bank_wm_boc", "daily", time(12, 0), 28),
    "bank_wm_bosc": UpdateCadence("bank_wm_bosc", "daily", time(12, 0), 28),
    "bank_wm_icbc": UpdateCadence("bank_wm_icbc", "daily", time(12, 0), 28),
    "crypto":    UpdateCadence("crypto",    "hourly", time(0, 0),  2),
}
"""Master cadence table — the single source of truth for update schedules."""


def get_cadence(asset_type: str) -> UpdateCadence:
    """Look up the UpdateCadence for *asset_type*, falling back to a
    sensible daily default when unknown."""
    if asset_type in CADENCE_TABLE:
        return CADENCE_TABLE[asset_type]
    # Normalize: strip _boc/_bosc/_icbc suffix and check generic entry
    for suffix in ("_boc", "_bosc", "_icbc"):
        if asset_type.endswith(suffix):
            generic = asset_type[: -len(suffix)]
            if generic in CADENCE_TABLE:
                return CADENCE_TABLE[generic]
    return UpdateCadence(asset_type, "daily", time(0, 0), 24)


def is_update_due(
    asset_type: str,
    last_updated_utc: datetime | None,
    now_utc: datetime | None = None,
) -> bool:
    """Check whether *asset_type* should be refreshed now.

    Args:
        asset_type: Asset type key (e.g. ``"us_equity"``).
        last_updated_utc: Timestamp of the last successful update, or
            ``None`` if the asset has never been updated.
        now_utc: Current UTC time (defaults to ``datetime.now(timezone.utc)``).

    Returns:
        ``True`` if a refresh is due now.
    """
    if now_utc is None:
        now_utc = datetime.now(timezone.utc)

    cadence = get_cadence(asset_type)

    # Never fetched → always due
    if last_updated_utc is None:
        return True

    # Ensure timezone-aware comparison
    if last_updated_utc.tzinfo is None:
        last_updated_utc = last_updated_utc.replace(tzinfo=timezone.utc)

    # Force refresh if data is too stale (exceeds max_stale_hours)
    age_hours = (now_utc - last_updated_utc).total_seconds() / 3600.0
    if age_hours >= cadence.max_stale_hours:
        return True

    # For "hourly" frequency: due if trigger time has passed since last update
    if cadence.frequency == "hourly":
        if age_hours >= 1.0:
            # Check if we're past the trigger time today
            trigger_today = now_utc.replace(
                hour=cadence.trigger_after_utc.hour,
                minute=cadence.trigger_after_utc.minute,
                second=0,
                microsecond=0,
            )
            if now_utc >= trigger_today:
                return True
        return False

    # For "daily" / "t+1_morning": due if trigger time has passed today
    # AND the last update was before today's trigger window
    trigger_today = now_utc.replace(
        hour=cadence.trigger_after_utc.hour,
        minute=cadence.trigger_after_utc.minute,
        second=0,
        microsecond=0,
    )
    if now_utc < trigger_today:
        # Trigger time hasn't arrived yet today
        return False

    if last_updated_utc >= trigger_today:
        return False

    return True

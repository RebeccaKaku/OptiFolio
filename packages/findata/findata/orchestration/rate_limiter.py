"""Per-provider rate limiting.

Each external data source imposes a maximum request frequency.
``RateLimiter`` enforces a minimum interval between calls so the
orchestrator never exceeds the provider's limit.
"""

from __future__ import annotations

import time


class RateLimiter:
    """Simple wall-clock throttle: enforces *max_per_second* calls/second.

    Usage::

        limiter = RateLimiter(10)   # 10 req/s max
        for url in urls:
            limiter.wait()
            fetch(url)
    """

    def __init__(self, max_per_second: float) -> None:
        if max_per_second <= 0:
            raise ValueError("max_per_second must be positive")
        self._interval: float = 1.0 / max_per_second
        self._last_call: float = 0.0

    def wait(self) -> None:
        """Block until at least ``_interval`` seconds have elapsed since
        the last call."""
        now = time.monotonic()
        elapsed = now - self._last_call
        if elapsed < self._interval:
            time.sleep(self._interval - elapsed)
        self._last_call = time.monotonic()

    @property
    def max_per_second(self) -> float:
        """The configured maximum call rate."""
        return 1.0 / self._interval


# ── Provider rate limits ────────────────────────────────────────────────

PROVIDER_LIMITS: dict[str, RateLimiter] = {
    "akshare-sina":       RateLimiter(10),   # Sina: 10 req/s
    "akshare-eastmoney":  RateLimiter(3),    # East Money: 3 req/s
    "akshare-cn-stock":   RateLimiter(5),
    "akshare-cn-fund":    RateLimiter(3),
    "akshare-boc-sina":   RateLimiter(5),
    "boc-wmp":            RateLimiter(1),    # BOC API: 1 req/s
    "bosc-wmp":           RateLimiter(1),
    "icbc-wmp":           RateLimiter(1),
    "yfinance":           RateLimiter(2),
}
"""Per-provider rate limiters.  Keys match ``FetchResult.provider`` values."""

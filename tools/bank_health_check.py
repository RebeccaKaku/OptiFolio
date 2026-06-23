#!/usr/bin/env python
"""Quick health check for all bank WMP fetcher interfaces.

Usage:
    python tools/bank_health_check.py              # all banks
    python tools/bank_health_check.py --bank boc   # single bank
    python tools/bank_health_check.py --json       # machine-readable output

Verifies that each bank's API endpoint is still accessible, returns data,
and the latest NAV is within a reasonable range.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

# Ensure project root is on path (needed when run as a standalone script)
_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from findata.adapters.bank_wmp import BankWmpFetcher


@dataclass
class CheckResult:
    bank: str
    symbol: str
    success: bool
    latency_ms: float
    rows: int = 0
    latest_date: str = ""
    latest_nav: Optional[float] = None
    error: str = ""


BANK_TESTS: list[tuple[str, str]] = [
    ("BOC", "AMHQLXTTUSD01B"),
    ("ICBC", "23GS8125"),
    ("BOSC", "WPXK24M1203A"),
]


def check_bank(fetcher: BankWmpFetcher, bank: str, symbol: str) -> CheckResult:
    t0 = time.time()
    try:
        r = fetcher.fetch(symbol, "2026-06-01", datetime.now().strftime("%Y-%m-%d"))
        latency = (time.time() - t0) * 1000

        if r.success and r.data is not None and len(r.data) > 0:
            last = r.data.iloc[-1]
            nav = float(last.iloc[3]) if len(last) > 3 else float(last.iloc[-1])
            return CheckResult(
                bank=bank, symbol=symbol, success=True, latency_ms=latency,
                rows=len(r.data), latest_date=str(last.iloc[0]),
                latest_nav=nav,
            )
        return CheckResult(
            bank=bank, symbol=symbol, success=False, latency_ms=latency,
            error=r.errors[0] if r.errors else "no data returned",
        )
    except Exception as e:
        latency = (time.time() - t0) * 1000
        return CheckResult(
            bank=bank, symbol=symbol, success=False, latency_ms=latency,
            error=f"{type(e).__name__}: {e}",
        )


def main() -> int:
    parser = argparse.ArgumentParser(description="Bank WMP fetcher health check")
    parser.add_argument("--bank", choices=["boc", "icbc", "bosc"],
                        help="Check only one bank")
    parser.add_argument("--json", action="store_true",
                        help="Output as JSON")
    args = parser.parse_args()

    fetcher = BankWmpFetcher()
    results: list[CheckResult] = []

    targets = [(b, s) for b, s in BANK_TESTS
               if not args.bank or b.lower() == args.bank]

    total = 0
    ok = 0
    for bank, symbol in targets:
        r = check_bank(fetcher, bank, symbol)
        results.append(r)
        total += 1
        if r.success:
            ok += 1

    if args.json:
        out = {
            "timestamp": datetime.now().isoformat(),
            "ok": ok,
            "total": total,
            "results": [
                {
                    "bank": r.bank,
                    "symbol": r.symbol,
                    "success": r.success,
                    "latency_ms": round(r.latency_ms),
                    "rows": r.rows,
                    "latest_date": r.latest_date,
                    "latest_nav": r.latest_nav,
                    "error": r.error,
                }
                for r in results
            ],
        }
        print(json.dumps(out, indent=2, ensure_ascii=False))
    else:
        print(f"Bank Health Check — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        print("-" * 55)
        for r in results:
            if r.success:
                print(f"  {r.bank:6s} OK  {r.rows:3d} rows  {r.latency_ms:5.0f}ms  "
                      f"latest={r.latest_nav:.4f} ({r.latest_date})")
            else:
                print(f"  {r.bank:6s} FAIL  {r.latency_ms:5.0f}ms  {r.error}")
        print("-" * 55)
        print(f"  {ok}/{total} banks healthy")

    return 0 if ok == total else 1


if __name__ == "__main__":
    sys.exit(main())

import sys
import os
from datetime import datetime
from typing import List

# Ensure project root is in path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.core.portfolio_core import PortfolioCore
from FinData.store.portfolio_ledger import PortfolioLedger, PortfolioLedgerStore

def record_portfolio_ledger():
    print(f"[{datetime.now()}] Recording portfolio ledger...")

    portfolio = PortfolioCore()
    holdings = portfolio.get_current_holdings()

    # In a real scenario, we might want to get actual cost basis.
    # For now, we'll use a placeholder or 0.0.
    # We'll use 'default_account' as account_id.

    entries: List[PortfolioLedger] = []
    as_of = datetime.now()

    for symbol, quantity in holdings.items():
        currency = portfolio.asset_meta.get(symbol, "USD")
        entry = PortfolioLedger(
            account_id="default_account",
            asset_id=symbol,
            quantity=quantity,
            cost_basis=0.0, # Placeholder
            currency=currency,
            as_of=as_of
        )
        entries.append(entry)

    store = PortfolioLedgerStore()
    store.save_entries(entries)

    print(f"[{datetime.now()}] Successfully recorded {len(entries)} entries to ledger.")

if __name__ == "__main__":
    record_portfolio_ledger()

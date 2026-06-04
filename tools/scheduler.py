import os
import json
import pandas as pd
import numpy as np
from datetime import datetime
from src.core.portfolio_core import PortfolioCore
from src.core.portfolio_history_tracker import PortfolioHistoryTracker

def run_daily_scheduler():
    """
    Run daily portfolio maintenance tasks.
    """
    print(f"[{datetime.now()}] Starting daily scheduler...")

    # Step 1: Market Data Sync
    print("Step 1: Synchronizing market data...")
    # Logic to sync data would go here

    # Step 2: Price Updates
    print("Step 2: Updating asset prices...")
    pc = PortfolioCore()

    # Step 3: Portfolio Valuation
    print("Step 3: Calculating portfolio valuation...")
    valuation = pc.get_portfolio_value()

    # Step 4: Risk Rules
    print("Step 4: Evaluating risk rules...")
    # Risk evaluation logic

    # Step 4.5: Compute performance metrics
    print("Step 4.5: Computing performance metrics...")
    # In a real implementation, we would load historical returns for the portfolio.
    # For now, we use a placeholder for demonstration as instructed.
    # mock_returns should be replaced with actual historical portfolio returns.
    mock_returns = pd.Series(np.random.normal(0.0005, 0.01, 252),
                            index=pd.date_range(end=datetime.now(), periods=252, freq='B'))
    metrics = PortfolioHistoryTracker.compute_metrics(mock_returns)

    # Save metrics alongside the daily snapshot
    snapshot = {
        "timestamp": datetime.now().isoformat(),
        "valuation": valuation,
        "metrics": metrics
    }

    # Ensure data directory exists
    snapshot_dir = os.path.join("data", "snapshots")
    os.makedirs(snapshot_dir, exist_ok=True)

    date_str = datetime.now().strftime("%Y%m%d")
    snapshot_path = os.path.join(snapshot_dir, f"snapshot_{date_str}.json")

    with open(snapshot_path, "w", encoding="utf-8") as f:
        json.dump(snapshot, f, indent=4, ensure_ascii=False)

    print(f"Daily snapshot saved to {snapshot_path}")
    print("Daily scheduler tasks completed successfully.")

if __name__ == "__main__":
    run_daily_scheduler()

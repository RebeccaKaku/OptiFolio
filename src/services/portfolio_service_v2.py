import os
import json
import pandas as pd
from typing import Dict, Any, Optional
from datetime import datetime, timedelta

from src.core.portfolio_history_tracker import PortfolioHistoryTracker
from src.api.enhanced_api_service import EnhancedAPIService
from .response import success, failure

class PortfolioServiceV2:
    def __init__(self, api_service: EnhancedAPIService):
        self.api_service = api_service
        self.snapshot_dir = os.path.join("data", "snapshots")

    def get_metrics(self) -> Dict[str, Any]:
        """
        Returns the latest metrics from the most recent snapshot.
        """
        try:
            if not os.path.exists(self.snapshot_dir):
                return failure("No snapshots found", "SNAPSHOT_NOT_FOUND")

            snapshots = sorted([f for f in os.listdir(self.snapshot_dir) if f.startswith("snapshot_")])
            if not snapshots:
                return failure("No snapshots found", "SNAPSHOT_NOT_FOUND")

            latest_snapshot_path = os.path.join(self.snapshot_dir, snapshots[-1])
            with open(latest_snapshot_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            return success(data.get("metrics", {}), "Latest metrics loaded")
        except Exception as e:
            return failure(str(e), "METRICS_FETCH_ERROR")

    def get_rolling_metrics(self, window: int = 60) -> Dict[str, Any]:
        """
        Computes and returns rolling metrics.
        """
        try:
            # In a real implementation, this would fetch historical portfolio returns.
            # Mocking returns for now as a placeholder.
            import numpy as np
            mock_returns = pd.Series(np.random.normal(0.0005, 0.01, 252),
                                    index=pd.date_range(end=datetime.now(), periods=252, freq='B'))

            rolling_df = PortfolioHistoryTracker.compute_rolling_metrics(mock_returns, window=window)

            # Format for JSON response
            data = {
                "window": window,
                "history": rolling_df.dropna().to_dict(orient="index")
            }
            # Convert datetime keys to strings
            data["history"] = {str(k): v for k, v in data["history"].items()}

            return success(data, f"Rolling metrics (window={window}) calculated")
        except Exception as e:
            return failure(str(e), "ROLLING_METRICS_ERROR")

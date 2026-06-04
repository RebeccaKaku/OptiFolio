"""FinData Fetcher Department — data retrieval only. No validation, no storage."""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
import time

@dataclass
class FetchResult:
    """Raw result from a data fetch operation."""
    symbol: str
    provider: str
    data: Any              # pd.DataFrame or similar — whatever the provider returned
    success: bool
    latency_ms: float
    errors: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

class FetcherProtocol:
    """Every fetcher must implement this. Fetch only — no validation, no storage."""
    def fetch(self, symbol: str, start_date: str, end_date: str, **kwargs) -> FetchResult:
        raise NotImplementedError

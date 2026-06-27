"""Future Qlib export boundary.

This module intentionally does not make Qlib a runtime dependency. The app keeps
canonical market data in OptiFolio's repository and can later add an exporter
here when factor or ML research becomes a first-class workflow.
"""

from __future__ import annotations

from pathlib import Path
from typing import Sequence

from src.infrastructure import HttpMarketDataClient, MarketDataGateway


class QlibAdapter:
    def __init__(self, market_data: MarketDataGateway | None = None) -> None:
        self.market_data = market_data or HttpMarketDataClient()

    def export(self, assets: Sequence[str], output_dir: str | Path) -> Path:
        raise NotImplementedError(
            "Qlib export is reserved for the factor/ML research phase and is not "
            "part of the first runnable asset-allocation path."
        )

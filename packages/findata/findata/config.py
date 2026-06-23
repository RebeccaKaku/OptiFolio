"""FinData configuration — data directory resolution without src/ dependency."""

from __future__ import annotations

import os
from pathlib import Path


class FinDataConfig:
    """Configuration for FinData storage paths.

    Replaces the old ``PROJECT_ROOT`` import from ``src.core.paths``.

    Default cache path precedence:
    1. Explicit ``data_dir`` argument
    2. ``FINDATA_HOME`` environment variable
    3. Project-level ``local/findata/`` (if project_root provided)
    4. User-level default (``~/.findata/``)
    """

    def __init__(
        self,
        data_dir: str | Path | None = None,
        project_root: str | Path | None = None,
    ) -> None:
        if data_dir:
            self.data_dir = Path(data_dir)
        elif env_home := os.environ.get("FINDATA_HOME"):
            self.data_dir = Path(env_home)
        elif project_root:
            self.data_dir = Path(project_root) / "local" / "findata"
        else:
            # Auto-detect: walk up from cwd to find project root
            auto_root = _detect_project_root()
            if auto_root:
                self.data_dir = auto_root / "local" / "findata"
            else:
                self.data_dir = Path.home() / ".findata"

        self.data_dir.mkdir(parents=True, exist_ok=True)

    @property
    def market_data_path(self) -> Path:
        """Path to the canonical market data Parquet file."""
        return self.data_dir / "market_prices.parquet"

    @property
    def observation_path(self) -> Path:
        """Path to the observations Parquet file."""
        return self.data_dir / "observations.parquet"

    @property
    def ingestion_log_path(self) -> Path:
        """Path to the ingestion log."""
        return self.data_dir / "ingestion_log.parquet"

    @property
    def bronze_dir(self) -> Path:
        """Path to the bronze (raw) data directory."""
        return self.data_dir / "bronze"


def _detect_project_root() -> Path | None:
    """Walk up from cwd to find project root (dir containing pyproject.toml)."""
    cwd = Path.cwd()
    for parent in [cwd, *cwd.parents]:
        if (parent / "pyproject.toml").exists():
            return parent
    return None


# Module-level default — callers should inject config explicitly
_default_config: FinDataConfig | None = None


def get_default_config() -> FinDataConfig:
    """Return the module-level default config, creating it on first call."""
    global _default_config
    if _default_config is None:
        _default_config = FinDataConfig()
    return _default_config

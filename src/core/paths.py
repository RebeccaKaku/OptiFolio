"""Runtime path helpers for private local state."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def get_local_dir() -> Path:
    configured = os.getenv("OPTIFOLIO_LOCAL_DIR")
    if configured:
        return Path(configured).expanduser().resolve()
    return PROJECT_ROOT / "local"


def resolve_private_file(
    env_var: str,
    local_name: str,
    legacy_relative_path: Optional[str] = None,
) -> Path:
    configured = os.getenv(env_var)
    if configured:
        return Path(configured).expanduser().resolve()

    local_path = get_local_dir() / local_name
    if local_path.exists():
        return local_path

    if legacy_relative_path:
        legacy_path = PROJECT_ROOT / legacy_relative_path
        if legacy_path.exists():
            return legacy_path

    return local_path


def get_portfolio_config_path() -> Path:
    return resolve_private_file(
        "OPTIFOLIO_PORTFOLIO_PATH",
        "portfolio.yaml",
        "config/portfolio.yaml",
    )


def get_database_path() -> Path:
    return resolve_private_file(
        "OPTIFOLIO_DB_PATH",
        "optifolio_db.db",
        "data/optifolio_db.db",
    )


def get_legacy_database_candidates() -> list[Path]:
    return [
        PROJECT_ROOT / "data" / "optifolio_db.db",
        PROJECT_ROOT / "data" / "optifolio.db",
    ]

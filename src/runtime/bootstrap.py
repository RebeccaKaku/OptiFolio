"""Initialize local private runtime files for OptiFolio."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Dict, Any

from src.core.database import DatabaseManager
from src.core.paths import (
    PROJECT_ROOT,
    get_database_path,
    get_legacy_database_candidates,
    get_local_dir,
    get_portfolio_config_path,
)


def _copy_if_missing(source: Path, destination: Path) -> bool:
    if destination.exists() or not source.exists():
        return False
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
    return True


def ensure_local_portfolio() -> Dict[str, Any]:
    local_portfolio = get_local_dir() / "portfolio.yaml"
    resolved_portfolio = get_portfolio_config_path()

    if local_portfolio.exists():
        return {"path": str(local_portfolio), "created": False, "source": "existing"}

    if resolved_portfolio.exists() and resolved_portfolio != local_portfolio:
        copied = _copy_if_missing(resolved_portfolio, local_portfolio)
        return {
            "path": str(local_portfolio),
            "created": copied,
            "source": str(resolved_portfolio),
        }

    example_path = PROJECT_ROOT / "config" / "portfolio.example.yaml"
    copied = _copy_if_missing(example_path, local_portfolio)
    return {
        "path": str(local_portfolio),
        "created": copied,
        "source": str(example_path) if copied else "missing-template",
    }


def ensure_local_database() -> Dict[str, Any]:
    local_db = get_local_dir() / "optifolio.db"
    configured_db = get_database_path()

    if local_db.exists():
        DatabaseManager(str(local_db)).close()
        return {"path": str(local_db), "created": False, "source": "existing"}

    if configured_db.exists() and configured_db != local_db:
        copied = _copy_if_missing(configured_db, local_db)
        DatabaseManager(str(local_db)).close()
        return {
            "path": str(local_db),
            "created": copied,
            "source": str(configured_db),
        }

    for legacy_path in get_legacy_database_candidates():
        if _copy_if_missing(legacy_path, local_db):
            DatabaseManager(str(local_db)).close()
            return {"path": str(local_db), "created": True, "source": str(legacy_path)}

    local_db.parent.mkdir(parents=True, exist_ok=True)
    DatabaseManager(str(local_db)).close()
    return {"path": str(local_db), "created": True, "source": "initialized"}


def bootstrap_local_state() -> Dict[str, Any]:
    get_local_dir().mkdir(parents=True, exist_ok=True)
    return {
        "local_dir": str(get_local_dir()),
        "portfolio": ensure_local_portfolio(),
        "database": ensure_local_database(),
    }


def main() -> int:
    result = bootstrap_local_state()
    print("OptiFolio local runtime is ready:")
    print(f"  local_dir: {result['local_dir']}")
    print(f"  portfolio: {result['portfolio']['path']} ({result['portfolio']['source']})")
    print(f"  database: {result['database']['path']} ({result['database']['source']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

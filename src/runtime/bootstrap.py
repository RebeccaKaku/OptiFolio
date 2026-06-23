"""Initialize local private runtime files for OptiFolio."""

from __future__ import annotations

import logging
import shutil
from pathlib import Path
from typing import Dict, Any

_log = logging.getLogger(__name__)

from src.core.paths import (
    PROJECT_ROOT,
    get_database_path,
    get_local_dir,
)


def _copy_if_missing(source: Path, destination: Path) -> bool:
    if destination.exists() or not source.exists():
        return False
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
    return True


def ensure_local_database() -> Dict[str, Any]:
    local_db = get_local_dir() / "portfolio_book.sqlite"
    configured_db = get_database_path()

    if local_db.exists():
        return {"path": str(local_db), "created": False, "source": "existing"}

    if configured_db.exists() and configured_db != local_db:
        copied = _copy_if_missing(configured_db, local_db)
        return {
            "path": str(local_db),
            "created": copied,
            "source": str(configured_db),
        }

    local_db.parent.mkdir(parents=True, exist_ok=True)
    return {"path": str(local_db), "created": True, "source": "initialized"}


def bootstrap_local_state() -> Dict[str, Any]:
    get_local_dir().mkdir(parents=True, exist_ok=True)
    return {
        "local_dir": str(get_local_dir()),
        "database": ensure_local_database(),
    }


def main() -> int:
    result = bootstrap_local_state()
    _log.info("OptiFolio local runtime is ready:")
    _log.info(f"  local_dir: {result['local_dir']}")
    _log.info(f"  database: {result['database']['path']} ({result['database']['source']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

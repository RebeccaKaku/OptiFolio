from pathlib import Path

from src.core.paths import get_database_path
from src.runtime.bootstrap import bootstrap_local_state


def test_bootstrap_creates_local_runtime_files(monkeypatch, tmp_path):
    local_dir = tmp_path / "local"
    monkeypatch.setenv("OPTIFOLIO_LOCAL_DIR", str(local_dir))
    monkeypatch.delenv("OPTIFOLIO_DB_PATH", raising=False)

    result = bootstrap_local_state()

    database_path = Path(result["database"]["path"])
    assert database_path == local_dir / "portfolio_book.sqlite"


def test_database_path_can_be_overridden(monkeypatch, tmp_path):
    db_path = tmp_path / "my_book.sqlite"
    monkeypatch.setenv("OPTIFOLIO_DB_PATH", str(db_path))

    assert get_database_path() == db_path.resolve()

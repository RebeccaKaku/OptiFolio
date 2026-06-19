from pathlib import Path

from src.runtime.bootstrap import bootstrap_local_state


def test_bootstrap_creates_local_runtime_files(monkeypatch, tmp_path):
    local_dir = tmp_path / "local"
    monkeypatch.setenv("OPTIFOLIO_LOCAL_DIR", str(local_dir))
    monkeypatch.delenv("OPTIFOLIO_PORTFOLIO_PATH", raising=False)
    monkeypatch.delenv("OPTIFOLIO_DB_PATH", raising=False)

    result = bootstrap_local_state()

    portfolio_path = Path(result["portfolio"]["path"])
    database_path = Path(result["database"]["path"])
    assert portfolio_path == local_dir / "portfolio.yaml"
    assert database_path == local_dir / "optifolio_db.db"
    assert portfolio_path.exists()


from src.core.paths import get_portfolio_config_path


def test_portfolio_path_can_be_overridden(monkeypatch, tmp_path):
    portfolio_path = tmp_path / "portfolio.yaml"
    monkeypatch.setenv("OPTIFOLIO_PORTFOLIO_PATH", str(portfolio_path))

    assert get_portfolio_config_path() == portfolio_path.resolve()

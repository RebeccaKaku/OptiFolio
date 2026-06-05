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
    assert database_path == local_dir / "optifolio.db"
    assert portfolio_path.exists()
    assert database_path.exists()


from pathlib import Path

from src.core.paths import get_portfolio_config_path
from src.core.portfolio_core import PortfolioCore


def test_portfolio_path_can_be_overridden(monkeypatch, tmp_path):
    portfolio_path = tmp_path / "portfolio.yaml"
    monkeypatch.setenv("OPTIFOLIO_PORTFOLIO_PATH", str(portfolio_path))

    assert get_portfolio_config_path() == portfolio_path.resolve()


def test_portfolio_core_loads_env_portfolio_path(monkeypatch, tmp_path):
    portfolio_path = tmp_path / "portfolio.yaml"
    portfolio_path.write_text(
        "cash:\n  USD: 12.5\npositions:\n  AAPL: 2\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("OPTIFOLIO_PORTFOLIO_PATH", str(portfolio_path))

    core = PortfolioCore(enable_cache=False)

    assert Path(core.config_path) == portfolio_path.resolve()
    assert core.get_cash_balances()["USD"] == 12.5
    assert core.get_current_holdings()["AAPL"] == 2.0

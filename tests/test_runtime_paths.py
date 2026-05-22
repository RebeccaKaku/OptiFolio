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

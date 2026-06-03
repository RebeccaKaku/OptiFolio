"""Tests for CorporateActionProcessor."""

from datetime import date

from src.core.corporate_actions import CorporateActionProcessor


class TestCorporateActionProcessor:
    """CRUD + apply logic."""

    def test_record_and_retrieve_dividend(self, tmp_path):
        cap = CorporateActionProcessor(tmp_path / "test_ca.yaml")
        cap.record_dividend("AAPL", date(2025, 6, 15), amount_per_share=0.50, currency="USD")

        actions = cap.get_actions(asset_id="AAPL")
        assert len(actions) == 1
        assert actions[0].asset_id == "AAPL"
        assert actions[0].action_type == "dividend"
        assert actions[0].dividend_per_share == 0.50

    def test_record_and_retrieve_split(self, tmp_path):
        cap = CorporateActionProcessor(tmp_path / "test_ca.yaml")
        cap.record_split("AAPL", date(2025, 8, 28), ratio=4.0)

        actions = cap.get_actions(asset_id="AAPL")
        assert len(actions) == 1
        assert actions[0].action_type == "stock_split"
        assert actions[0].split_ratio == 4.0

    def test_filter_by_date_range(self, tmp_path):
        cap = CorporateActionProcessor(tmp_path / "test_ca.yaml")
        cap.record_dividend("AAPL", date(2025, 3, 15), amount_per_share=0.50)
        cap.record_dividend("AAPL", date(2025, 6, 15), amount_per_share=0.60)
        cap.record_dividend("AAPL", date(2025, 9, 15), amount_per_share=0.70)

        q2 = cap.get_actions(from_date=date(2025, 4, 1), to_date=date(2025, 7, 31))
        assert len(q2) == 1
        assert q2[0].dividend_per_share == 0.60

    def test_apply_to_holdings_dividend(self, tmp_path):
        cap = CorporateActionProcessor(tmp_path / "test_ca.yaml")
        cap.record_dividend("AAPL", date(2025, 6, 15), amount_per_share=1.0, currency="USD")

        h, c, adj = cap.apply_to_holdings(
            {"AAPL": 100}, {"USD": 500},
            up_to_date=date(2025, 6, 20),
        )
        assert h["AAPL"] == 100  # holdings unchanged
        assert c["USD"] == 600  # 500 + 100
        assert adj == 100.0

    def test_apply_to_holdings_split(self, tmp_path):
        cap = CorporateActionProcessor(tmp_path / "test_ca.yaml")
        cap.record_split("AAPL", date(2025, 8, 28), ratio=4.0)

        h, c, adj = cap.apply_to_holdings(
            {"AAPL": 100}, {"USD": 0},
            up_to_date=date(2025, 9, 1),
        )
        assert h["AAPL"] == 400
        assert adj == 0.0

    def test_apply_chronological_order(self, tmp_path):
        """Split before dividend — dividend applies to post-split shares."""
        cap = CorporateActionProcessor(tmp_path / "test_ca.yaml")
        cap.record_split("AAPL", date(2025, 6, 1), ratio=2.0)
        cap.record_dividend("AAPL", date(2025, 6, 15), amount_per_share=1.0)

        h, c, adj = cap.apply_to_holdings(
            {"AAPL": 100}, {"USD": 0},
            up_to_date=date(2025, 7, 1),
        )
        assert h["AAPL"] == 200  # 100 * 2
        assert c["USD"] == 200  # 200 shares * $1
        assert adj == 200.0

    def test_merger_exchanges_holdings(self, tmp_path):
        cap = CorporateActionProcessor(tmp_path / "test_ca.yaml")
        cap.record_merger(
            "OLDCO", "NEWCO", date(2025, 9, 1),
            exchange_ratio=0.5, cash_per_share=3.0, cash_currency="USD",
        )

        h, c, adj = cap.apply_to_holdings(
            {"OLDCO": 200}, {"USD": 0},
            up_to_date=date(2025, 9, 15),
        )
        assert "OLDCO" not in h
        assert h["NEWCO"] == 100  # 200 * 0.5
        assert c["USD"] == 600   # 200 * 3.0
        assert adj == 600.0

    def test_persistence_roundtrip(self, tmp_path):
        path = tmp_path / "test_ca.yaml"
        cap1 = CorporateActionProcessor(path)
        cap1.record_dividend("QQQ", date(2025, 3, 15), amount_per_share=0.50)

        cap2 = CorporateActionProcessor(path)
        actions = cap2.get_actions(asset_id="QQQ")
        assert len(actions) == 1
        assert actions[0].dividend_per_share == 0.50

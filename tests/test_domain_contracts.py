"""Tests for domain contracts — construction, immutability, and to_dict roundtrip."""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from datetime import date, datetime

import pytest

from src.domain.cashflows import CashflowEvent
from src.domain.instruments import InstrumentDefinition
from src.domain.observations import Observation
from src.domain.positions import PositionSnapshot
from src.domain.products import ProductDefinition
from src.domain.relationships import (
    ExposureDefinition,
    PayoffDefinition,
    PortfolioComponent,
    PortfolioDefinition,
    UnderlyingLink,
)
from src.domain.series import SeriesDefinition


# ── Helpers ────────────────────────────────────────────────────────────

TODAY = date.today()
SOME_DATETIME = datetime(2026, 6, 3, 12, 0, 0)


def _assert_frozen(obj: object) -> None:
    """Verify that setting an attribute on a frozen dataclass raises."""
    from dataclasses import FrozenInstanceError

    with pytest.raises(FrozenInstanceError):
        obj._test_field = "should_fail"  # type: ignore[attr-defined]


# ── D1 — Product / Position / Cashflow ─────────────────────────────────


class TestProductDefinition:
    def test_construction_minimal(self):
        p = ProductDefinition(product_id="PD001", name="Test Deposit", product_type="deposit")
        assert p.product_id == "PD001"
        assert p.currency == "CNY"
        assert p.issuer is None
        assert p.metadata == {}
        assert is_dataclass(p)
        _assert_frozen(p)

    def test_construction_full(self):
        p = ProductDefinition(
            product_id="PD002",
            name="Enhanced Deposit",
            product_type="structured_deposit",
            issuer="Some Bank",
            manager="Manager Co",
            currency="CNY",
            risk_level="R2",
            liquidity_type="T+1",
            fee_policy_id="FP1",
            benchmark_id="BM1",
            primary_instrument_id="INST001",
            data_source="manual",
            metadata={"rating": "AAA"},
        )
        assert p.risk_level == "R2"
        assert p.metadata["rating"] == "AAA"

    def test_to_dict(self):
        p = ProductDefinition(
            product_id="PD003",
            name="Bond Fund",
            product_type="bond_fund",
            issuer="Issuer A",
            metadata={"key": "val"},
        )
        d = p.to_dict()
        assert d["product_id"] == "PD003"
        assert d["name"] == "Bond Fund"
        assert d["product_type"] == "bond_fund"
        assert d["issuer"] == "Issuer A"
        assert d["currency"] == "CNY"
        assert d["metadata"] == {"key": "val"}


class TestPositionSnapshot:
    def test_construction(self):
        ps = PositionSnapshot(
            date=TODAY,
            account_id="ACC1",
            product_id="PD001",
            quantity=1000.0,
            market_value=105000.0,
            cost_basis=100000.0,
        )
        assert ps.date == TODAY
        assert ps.account_id == "ACC1"
        assert ps.product_id == "PD001"
        assert ps.quantity == 1000.0
        assert ps.market_value == 105000.0
        assert ps.cost_basis == 100000.0
        assert ps.currency == "CNY"
        assert ps.available_amount is None
        assert ps.lockup_end_date is None
        assert is_dataclass(ps)
        _assert_frozen(ps)

    def test_to_dict(self):
        lockup = date(2027, 6, 3)
        ps = PositionSnapshot(
            date=TODAY,
            account_id="ACC2",
            product_id="PD002",
            market_value=50000.0,
            lockup_end_date=lockup,
        )
        d = ps.to_dict()
        assert d["date"] == TODAY.isoformat()
        assert d["account_id"] == "ACC2"
        assert d["market_value"] == 50000.0
        assert d["lockup_end_date"] == lockup.isoformat()
        assert d["available_amount"] is None


class TestCashflowEvent:
    def test_construction(self):
        cf = CashflowEvent(
            event_id="EVT001",
            product_id="PD001",
            account_id="ACC1",
            event_type="purchase",
            trade_date=TODAY,
            settle_date=date(2026, 6, 5),
            amount=100000.0,
            units=1000.0,
        )
        assert cf.event_id == "EVT001"
        assert cf.product_id == "PD001"
        assert cf.event_type == "purchase"
        assert cf.amount == 100000.0
        assert cf.units == 1000.0
        assert cf.currency == "CNY"
        assert cf.source == "manual"
        assert is_dataclass(cf)
        _assert_frozen(cf)

    def test_to_dict(self):
        settle = date(2026, 6, 5)
        cf = CashflowEvent(
            event_id="EVT002",
            product_id="PD002",
            event_type="coupon",
            trade_date=TODAY,
            settle_date=settle,
            amount=500.0,
            known_at=SOME_DATETIME,
            metadata={"note": "quarterly"},
        )
        d = cf.to_dict()
        assert d["event_id"] == "EVT002"
        assert d["trade_date"] == TODAY.isoformat()
        assert d["settle_date"] == settle.isoformat()
        assert d["known_at"] == SOME_DATETIME.isoformat()
        assert d["metadata"] == {"note": "quarterly"}


# ── D2 — Instrument / Series / Observation ─────────────────────────────


class TestInstrumentDefinition:
    def test_construction(self):
        inst = InstrumentDefinition(
            instrument_id="INST001",
            symbol="000001.SZ",
            name="Ping An Bank",
            instrument_type="equity",
        )
        assert inst.instrument_id == "INST001"
        assert inst.symbol == "000001.SZ"
        assert inst.instrument_type == "equity"
        assert inst.quote_currency == "CNY"
        assert inst.tradable is True
        assert inst.valuation_method == "ohlcv_close"
        assert is_dataclass(inst)
        _assert_frozen(inst)

    def test_empty_instrument_id_is_allowed(self):
        """Business rule note: the dataclass does NOT reject an empty
        instrument_id.  Validation is the caller's responsibility (service /
        repository layer).  This test documents that the type system alone
        does not enforce non-empty-string constraints."""
        inst = InstrumentDefinition(instrument_id="", symbol="", name="empty")
        assert inst.instrument_id == ""

    def test_to_dict(self):
        inst = InstrumentDefinition(
            instrument_id="INST002",
            symbol="511880.SH",
            name="Huatai-PB Money Market ETF",
            instrument_type="fund",
            exchange_id="SSE",
            valuation_method="published_nav",
            metadata={"category": "money_market"},
        )
        d = inst.to_dict()
        assert d["instrument_id"] == "INST002"
        assert d["symbol"] == "511880.SH"
        assert d["instrument_type"] == "fund"
        assert d["exchange_id"] == "SSE"
        assert d["valuation_method"] == "published_nav"
        assert d["metadata"] == {"category": "money_market"}


class TestSeriesDefinition:
    def test_construction(self):
        s = SeriesDefinition(
            series_id="CSI300",
            series_type="index_level",
            subject_id="CSI300",
            frequency="D",
            unit="points",
            currency="CNY",
        )
        assert s.series_id == "CSI300"
        assert s.series_type == "index_level"
        assert s.frequency == "D"
        assert s.unit == "points"
        assert s.source_priority == ()
        assert s.revision_policy == "append_only"
        assert is_dataclass(s)
        _assert_frozen(s)

    def test_to_dict(self):
        s = SeriesDefinition(
            series_id="SHIBOR_ON",
            series_type="yield_curve",
            subject_id="SHIBOR",
            frequency="D",
            unit="percent",
            source_priority=("PBOC", "Wind"),
            metadata={"tenor": "ON"},
        )
        d = s.to_dict()
        assert d["series_id"] == "SHIBOR_ON"
        assert d["series_type"] == "yield_curve"
        assert d["source_priority"] == ["PBOC", "Wind"]
        assert d["metadata"] == {"tenor": "ON"}

    def test_different_from_instrument_definition(self):
        """SeriesDefinition describes a time-series data stream (e.g. an index
        level or macro indicator), whereas InstrumentDefinition describes a
        tradable financial instrument.  They are different types with different
        fields and purposes — one is NOT interchangeable with the other."""
        s = SeriesDefinition(
            series_id="CSI300",
            series_type="index_level",
            subject_id="CSI300",
            frequency="D",
            unit="points",
        )
        inst = InstrumentDefinition(
            instrument_id="511880.SH",
            symbol="511880.SH",
            instrument_type="fund",
        )
        # They are different types entirely
        assert not isinstance(s, InstrumentDefinition)
        assert not isinstance(inst, SeriesDefinition)
        # They have non-overlapping required fields
        assert hasattr(s, "series_type")
        assert hasattr(inst, "instrument_type")
        assert not hasattr(s, "instrument_type")
        assert not hasattr(inst, "series_type")


class TestObservation:
    def test_construction(self):
        obs = Observation(
            series_id="CSI300",
            effective_date=TODAY,
            value=3850.5,
        )
        assert obs.series_id == "CSI300"
        assert obs.effective_date == TODAY
        assert obs.value == 3850.5
        assert obs.known_at is None
        assert obs.revision == 0
        assert obs.quality_flags == ()
        assert is_dataclass(obs)
        _assert_frozen(obs)

    def test_known_at_before_effective_date_is_not_enforced(self):
        """Business rule note: in a live system, known_at should NOT be before
        effective_date (you cannot know a price before the date it refers to).
        However, the dataclass deliberately does NOT enforce this constraint —
        it is a business rule enforced by the repository / service layer.

        This test constructs an Observation where known_at precedes
        effective_date and confirms that construction succeeds, documenting
        that the type system alone does not prevent this."""
        yesterday = date(2026, 6, 2)
        next_week = date(2026, 6, 10)
        obs = Observation(
            series_id="CSI300",
            effective_date=next_week,  # June 10
            value=4000.0,
            known_at=datetime(2026, 6, 2, 12, 0, 0),  # June 2 — before effective_date!
        )
        assert obs.effective_date == next_week
        assert obs.known_at == datetime(2026, 6, 2, 12, 0, 0)
        # The invariant is VIOLATED and the dataclass allows it — as designed.
        assert obs.known_at.date() < obs.effective_date

    def test_to_dict(self):
        obs = Observation(
            series_id="SHIBOR_ON",
            effective_date=TODAY,
            value=1.85,
            known_at=SOME_DATETIME,
            released_at=SOME_DATETIME,
            observed_at=SOME_DATETIME,
            source="Wind",
            revision=1,
            quality_flags=("estimated",),
        )
        d = obs.to_dict()
        assert d["series_id"] == "SHIBOR_ON"
        assert d["effective_date"] == TODAY.isoformat()
        assert d["value"] == 1.85
        assert d["known_at"] == SOME_DATETIME.isoformat()
        assert d["revision"] == 1
        assert d["quality_flags"] == ["estimated"]


# ── D3 — Relationships ────────────────────────────────────────────────


class TestPortfolioComponent:
    def test_construction(self):
        pc = PortfolioComponent(
            target_id="INST001",
            target_kind="instrument",
            weight=0.5,
        )
        assert pc.target_id == "INST001"
        assert pc.target_kind == "instrument"
        assert pc.weight == 0.5
        assert pc.role == "holding"
        assert is_dataclass(pc)
        _assert_frozen(pc)

    def test_to_dict(self):
        pc = PortfolioComponent(target_id="SERIES_CSI300", target_kind="series", role="benchmark")
        d = pc.to_dict()
        assert d["target_id"] == "SERIES_CSI300"
        assert d["target_kind"] == "series"
        assert d["role"] == "benchmark"


class TestPortfolioDefinition:
    def test_construction(self):
        pd_ = PortfolioDefinition(portfolio_id="PF001", name="My Portfolio")
        assert pd_.portfolio_id == "PF001"
        assert pd_.name == "My Portfolio"
        assert pd_.components == ()
        assert pd_.weighting_policy == "equal_weight"
        assert is_dataclass(pd_)
        _assert_frozen(pd_)

    def test_with_components(self):
        c1 = PortfolioComponent(target_id="INST001", weight=0.6)
        c2 = PortfolioComponent(target_id="INST002", weight=0.4)
        pd_ = PortfolioDefinition(
            portfolio_id="PF002",
            name="Balanced",
            components=(c1, c2),
            weighting_policy="target_weight",
            rebalance_policy="threshold_5pct",
        )
        assert len(pd_.components) == 2
        assert pd_.components[0].target_id == "INST001"
        assert pd_.rebalance_policy == "threshold_5pct"

    def test_to_dict(self):
        c = PortfolioComponent(target_id="INST001", weight=1.0)
        pd_ = PortfolioDefinition(
            portfolio_id="PF003",
            name="Single Asset",
            components=(c,),
            currency="CNY",
            metadata={"benchmark": "CSI300"},
        )
        d = pd_.to_dict()
        assert d["portfolio_id"] == "PF003"
        assert d["components"][0]["target_id"] == "INST001"
        assert d["metadata"] == {"benchmark": "CSI300"}


class TestUnderlyingLink:
    def test_construction(self):
        ul = UnderlyingLink(
            owner_id="INST001",
            underlying_id="PF001",
            relationship_type="holds",
        )
        assert ul.owner_id == "INST001"
        assert ul.underlying_id == "PF001"
        assert ul.owner_kind == "instrument"
        assert ul.underlying_kind == "portfolio"
        assert ul.relationship_type == "holds"
        assert ul.lookthrough_policy == "none"
        assert ul.valid_from is None
        assert ul.valid_to is None
        assert is_dataclass(ul)
        _assert_frozen(ul)

    def test_to_dict(self):
        vf = date(2026, 1, 1)
        vt = date(2026, 12, 31)
        ul = UnderlyingLink(
            owner_id="INST002",
            owner_kind="instrument",
            underlying_id="INDEX_CSI300",
            underlying_kind="series",
            relationship_type="tracks",
            lookthrough_policy="holdings",
            valid_from=vf,
            valid_to=vt,
            metadata={"tracking_error_target": 0.02},
        )
        d = ul.to_dict()
        assert d["owner_id"] == "INST002"
        assert d["relationship_type"] == "tracks"
        assert d["valid_from"] == vf.isoformat()
        assert d["valid_to"] == vt.isoformat()
        assert d["metadata"] == {"tracking_error_target": 0.02}


class TestExposureDefinition:
    def test_construction(self):
        ed = ExposureDefinition(
            exposure_id="IR_DURATION",
            reference_series_id="CNBOND_5Y",
            tradable_proxy_ids=("TF2306", "TF2309"),
            default_proxy_id="TF2306",
        )
        assert ed.exposure_id == "IR_DURATION"
        assert ed.reference_series_id == "CNBOND_5Y"
        assert ed.tradable_proxy_ids == ("TF2306", "TF2309")
        assert ed.default_proxy_id == "TF2306"
        assert ed.hedge_ratio_policy == "one_to_one"
        assert is_dataclass(ed)
        _assert_frozen(ed)

    def test_to_dict(self):
        ed = ExposureDefinition(
            exposure_id="FX_USDCNY",
            reference_series_id="USDCNY_MID",
            metadata={"category": "currency"},
        )
        d = ed.to_dict()
        assert d["exposure_id"] == "FX_USDCNY"
        assert d["tradable_proxy_ids"] == []
        assert d["metadata"] == {"category": "currency"}


class TestPayoffDefinition:
    def test_construction(self):
        pd_ = PayoffDefinition(
            payoff_id="PAYOFF001",
            owner_instrument_id="INST_STRUCT001",
            underlying_refs=("CSI300", "SSE50"),
            payoff_type="snowball",
            parameters={"barrier": 0.8, "coupon": 0.15},
            valuation_model="monte_carlo",
            greeks_policy="finite_difference",
        )
        assert pd_.payoff_id == "PAYOFF001"
        assert pd_.owner_instrument_id == "INST_STRUCT001"
        assert pd_.payoff_type == "snowball"
        assert pd_.parameters["barrier"] == 0.8
        assert pd_.valuation_model == "monte_carlo"
        assert is_dataclass(pd_)
        _assert_frozen(pd_)

    def test_to_dict(self):
        pd_ = PayoffDefinition(
            payoff_id="PAYOFF002",
            owner_instrument_id="INST_ETF001",
            underlying_refs=("CSI300",),
            payoff_type="linear",
        )
        d = pd_.to_dict()
        assert d["payoff_id"] == "PAYOFF002"
        assert d["underlying_refs"] == ["CSI300"]
        assert d["payoff_type"] == "linear"
        assert d["valuation_model"] == "none"


# ── Cross-type assertions ──────────────────────────────────────────────


def test_all_new_types_are_frozen_dataclasses():
    """Every new domain contract must be a frozen dataclass."""
    types_to_check = [
        ProductDefinition,
        PositionSnapshot,
        CashflowEvent,
        InstrumentDefinition,
        SeriesDefinition,
        Observation,
        PortfolioComponent,
        PortfolioDefinition,
        UnderlyingLink,
        ExposureDefinition,
        PayoffDefinition,
    ]
    for cls in types_to_check:
        assert is_dataclass(cls), f"{cls.__name__} is not a dataclass"
        assert cls.__dataclass_params__.frozen, f"{cls.__name__} is not frozen"

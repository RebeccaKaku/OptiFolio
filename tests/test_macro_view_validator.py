"""Tests for MacroViewValidator."""

from datetime import datetime, timedelta
import pytest
from dataclasses import replace

from src.domain.macro_view import MacroView, Evidence, Scenario
from src.services.macro_view_validator import MacroViewValidator


@pytest.fixture
def base_view():
    as_of = datetime(2024, 6, 1)
    cutoff = datetime(2024, 5, 31, 23, 59, 59)
    created_at = datetime(2024, 6, 1, 10, 0, 0)
    expires_at = datetime(2024, 7, 1)

    supporting = [
        Evidence(
            series_or_source_ref="FED_FUNDS_RATE",
            observed_at=datetime(2024, 5, 1),
            known_at=datetime(2024, 5, 2),
            summary="Fed holds rates steady",
            direction="neutral"
        )
    ]
    opposing = [
        Evidence(
            series_or_source_ref="US_CPI",
            observed_at=datetime(2024, 5, 15),
            known_at=datetime(2024, 5, 16),
            summary="CPI higher than expected",
            direction="bearish"
        )
    ]
    scenarios = [
        Scenario(
            name="Soft Landing",
            probability=0.7,
            assumptions=["Inflation continues to cool"],
            calculator_inputs={"equity_risk_premium": 0.05}
        ),
        Scenario(
            name="Recession",
            probability=0.3,
            assumptions=["Rates stay high for longer"],
            calculator_inputs={"equity_risk_premium": 0.08}
        )
    ]

    return MacroView(
        view_id="view-001",
        version="1.0",
        as_of=as_of,
        observation_cutoff=cutoff,
        scope="Global Macro",
        horizon="6 months",
        claim="The US economy will avoid a recession in 2024.",
        supporting_evidence=supporting,
        opposing_evidence=opposing,
        scenarios=scenarios,
        confidence=0.8,
        invalidation_conditions=["Unemployment rises above 5%"],
        expires_at=expires_at,
        author_model="gpt-4o-2024-05-13",
        created_at=created_at
    )


def test_valid_view(base_view):
    validator = MacroViewValidator()
    result = validator.validate(base_view)
    assert result.valid_for_experiment is True
    assert not result.errors


def test_missing_opposing_evidence(base_view):
    view = replace(base_view, opposing_evidence=[])
    validator = MacroViewValidator()
    result = validator.validate(view)
    assert result.valid_for_experiment is False
    assert "Missing opposing evidence" in result.errors


def test_probability_boundary(base_view):
    # Sum to 1.1
    s1 = replace(base_view.scenarios[0], probability=0.8)
    view = replace(base_view, scenarios=[s1, base_view.scenarios[1]])
    validator = MacroViewValidator()
    result = validator.validate(view)
    assert result.valid_for_experiment is False
    assert "Scenario probabilities sum to 1.1" in result.errors[0]

    # Individual out of range
    s1 = replace(base_view.scenarios[0], probability=1.2)
    s2 = replace(base_view.scenarios[1], probability=-0.2)
    view = replace(base_view, scenarios=[s1, s2])
    result = validator.validate(view)
    assert result.valid_for_experiment is False
    assert any("out of range" in e for e in result.errors)


def test_expiration_logic(base_view):
    # Expired relative to as_of
    view = replace(base_view, expires_at=base_view.as_of - timedelta(days=1))
    validator = MacroViewValidator()
    result = validator.validate(view)
    assert result.valid_for_experiment is False
    assert "View is expired" in result.errors[0]


def test_future_evidence(base_view):
    # Evidence known_at > cutoff
    future_ev = replace(base_view.supporting_evidence[0], known_at=base_view.observation_cutoff + timedelta(hours=1))
    view = replace(base_view, supporting_evidence=[future_ev])
    validator = MacroViewValidator()
    result = validator.validate(view)
    assert result.valid_for_experiment is False
    assert "is after observation_cutoff" in result.errors[0]


def test_trade_instruction_injection(base_view):
    # Injection in key
    s1 = Scenario(
        name="Bad Scenario",
        probability=1.0,
        assumptions=[],
        calculator_inputs={"BUY_TICKER_AAPL": 100}
    )
    view = replace(base_view, scenarios=[s1])
    validator = MacroViewValidator()
    result = validator.validate(view)
    assert result.valid_for_experiment is False
    assert "contains forbidden keyword in key" in result.errors[0]

    # Injection in value
    s2 = Scenario(
        name="Bad Scenario 2",
        probability=1.0,
        assumptions=[],
        calculator_inputs={"note": "Order now!"}
    )
    view = replace(base_view, scenarios=[s2])
    result = validator.validate(view)
    assert result.valid_for_experiment is False
    assert "contains forbidden keyword in value" in result.errors[0]


def test_missing_invalidation_conditions(base_view):
    view = replace(base_view, invalidation_conditions=[])
    validator = MacroViewValidator()
    result = validator.validate(view)
    assert result.valid_for_experiment is False
    assert "Missing invalidation conditions" in result.errors


def test_confidence_range(base_view):
    view = replace(base_view, confidence=1.5)
    validator = MacroViewValidator()
    result = validator.validate(view)
    assert result.valid_for_experiment is False
    assert "Confidence 1.5 out of range [0, 1]" in result.errors

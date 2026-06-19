"""Macro View domain models — AI-generated macro judgments."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class Evidence:
    """A piece of evidence supporting or opposing a macro view."""
    series_or_source_ref: str
    observed_at: datetime
    known_at: datetime
    summary: str
    direction: str  # e.g., "bullish", "bearish", "neutral"


@dataclass(frozen=True)
class Scenario:
    """A possible future scenario under a macro view."""
    name: str
    probability: float
    assumptions: List[str]
    calculator_inputs: Dict[str, Any]


@dataclass(frozen=True)
class MacroView:
    """A structured AI macro judgment."""
    view_id: str
    version: str
    as_of: datetime
    observation_cutoff: datetime
    scope: str
    horizon: str
    claim: str
    supporting_evidence: List[Evidence]
    opposing_evidence: List[Evidence]
    scenarios: List[Scenario]
    confidence: float
    invalidation_conditions: List[str]
    expires_at: datetime
    author_model: str
    created_at: datetime

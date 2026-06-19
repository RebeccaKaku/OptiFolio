"""Validator for AI Macro Views."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Set

from src.domain.macro_view import MacroView, Evidence, Scenario


@dataclass(frozen=True)
class ValidationResult:
    """Result of macro view validation."""
    valid_for_experiment: bool
    valid_for_calculator_candidate: bool
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


class MacroViewValidator:
    """Validates the structure and consistency of a MacroView."""

    FORBIDDEN_KEYWORDS = {"buy", "sell", "ticker", "amount", "order"}

    def validate(self, view: MacroView) -> ValidationResult:
        errors = []
        warnings = []

        # 1. Structural checks & Missing Dates
        if not view.opposing_evidence:
            errors.append("Missing opposing evidence")

        if not view.invalidation_conditions:
            errors.append("Missing invalidation conditions")

        # Check for essential dates (missing dates check)
        date_fields = {
            "as_of": view.as_of,
            "observation_cutoff": view.observation_cutoff,
            "expires_at": view.expires_at,
            "created_at": view.created_at
        }
        for name, val in date_fields.items():
            if val is None:
                errors.append(f"Missing date: {name}")

        # 2. Confidence check
        if view.confidence is None:
             errors.append("Missing confidence")
        elif not (0.0 <= view.confidence <= 1.0):
            errors.append(f"Confidence {view.confidence} out of range [0, 1]")

        # 3. Time consistency checks
        if view.as_of and view.expires_at:
            if view.expires_at <= view.as_of:
                errors.append(f"View is expired: expires_at ({view.expires_at}) <= as_of ({view.as_of})")

        if view.observation_cutoff:
            for i, ev in enumerate(view.supporting_evidence):
                if ev.known_at is None:
                    errors.append(f"Supporting evidence {i} missing known_at")
                elif ev.known_at > view.observation_cutoff:
                    errors.append(f"Supporting evidence {i} known_at ({ev.known_at}) is after observation_cutoff ({view.observation_cutoff})")

            for i, ev in enumerate(view.opposing_evidence):
                if ev.known_at is None:
                    errors.append(f"Opposing evidence {i} missing known_at")
                elif ev.known_at > view.observation_cutoff:
                    errors.append(f"Opposing evidence {i} known_at ({ev.known_at}) is after observation_cutoff ({view.observation_cutoff})")

        # 4. Scenario checks
        if not view.scenarios:
            errors.append("No scenarios provided")
        else:
            total_prob = sum(s.probability for s in view.scenarios if s.probability is not None)
            if not math.isclose(total_prob, 1.0, rel_tol=1e-7):
                errors.append(f"Scenario probabilities sum to {total_prob}, expected 1.0")

            for i, s in enumerate(view.scenarios):
                if s.probability is None:
                    errors.append(f"Scenario {i} missing probability")
                elif not (0.0 <= s.probability <= 1.0):
                    errors.append(f"Scenario {i} probability {s.probability} out of range [0, 1]")

                # Forbidden keywords in calculator_inputs
                if s.calculator_inputs:
                    for key in s.calculator_inputs:
                        key_lower = key.lower()
                        if any(kw in key_lower for kw in self.FORBIDDEN_KEYWORDS):
                            errors.append(f"Scenario {i} calculator_inputs contains forbidden keyword in key: {key}")

                        val = s.calculator_inputs[key]
                        if isinstance(val, str):
                            val_lower = val.lower()
                            if any(kw in val_lower for kw in self.FORBIDDEN_KEYWORDS):
                                errors.append(f"Scenario {i} calculator_inputs contains forbidden keyword in value: {val}")

        valid_for_experiment = len(errors) == 0
        # For this contract, calculator candidate requires the same structural validity.
        # Promotion to actual usage is handled by DS-027.
        valid_for_calculator_candidate = valid_for_experiment

        return ValidationResult(
            valid_for_experiment=valid_for_experiment,
            valid_for_calculator_candidate=valid_for_calculator_candidate,
            errors=errors,
            warnings=warnings
        )

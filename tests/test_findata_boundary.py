"""Import-boundary tests for the package layer cake.

Dependency rule:
    optifolio_contracts
        ↑
        ├── findata
        └── src / OptiFolio app

* ``packages/optifolio_contracts`` must not import ``src`` or ``findata``.
* ``packages/findata`` must not import ``src``.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PACKAGES = ROOT / "packages"

# Regexes that indicate a forbidden import statement.
FORBIDDEN_SRC_IMPORT = re.compile(r"(^\s*(?:from\s+src\.?|import\s+src\.?))", re.MULTILINE)
FORBIDDEN_FINDATA_IMPORT = re.compile(r"(^\s*(?:from\s+findata\.?|import\s+findata\.?))", re.MULTILINE)


def _py_files(directory: Path):
    if not directory.exists():
        return []
    return [p for p in directory.rglob("*.py") if "__pycache__" not in p.parts]


def _check_no_forbidden(directory: Path, forbidden: list[tuple[str, re.Pattern]]) -> list[str]:
    violations: list[str] = []
    for path in _py_files(directory):
        text = path.read_text(encoding="utf-8")
        for name, pattern in forbidden:
            if pattern.search(text):
                violations.append(f"{path.relative_to(ROOT)}: forbidden {name} import")
    return violations


class TestOptifolioContractsBoundary:
    """``optifolio_contracts`` must remain pure: no src, no findata."""

    def test_no_src_or_findata_imports(self):
        package = PACKAGES / "optifolio_contracts"
        assert package.exists(), "optifolio_contracts package not found"
        violations = _check_no_forbidden(
            package,
            [("src", FORBIDDEN_SRC_IMPORT), ("findata", FORBIDDEN_FINDATA_IMPORT)],
        )
        assert not violations, "\n".join(violations)


class TestFindataBoundary:
    """``findata`` may import ``optifolio_contracts`` but never ``src``."""

    def test_no_src_imports(self):
        package = PACKAGES / "findata"
        assert package.exists(), "findata package not found"
        violations = _check_no_forbidden(package, [("src", FORBIDDEN_SRC_IMPORT)])
        assert not violations, "\n".join(violations)

"""Architecture boundary tests after FinDataProvider extraction."""

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _imports_under(path: Path):
    for file in path.rglob("*.py"):
        tree = ast.parse(file.read_text(encoding="utf-8-sig"), filename=str(file))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    yield file, alias.name
            elif isinstance(node, ast.ImportFrom) and node.module:
                yield file, node.module


def test_findata_runtime_is_not_embedded_in_optifolio():
    assert not (ROOT / "packages" / "findata").exists()


def test_application_does_not_import_findata_package():
    violations = [
        str(file.relative_to(ROOT))
        for file, module in _imports_under(ROOT / "src")
        if module == "findata" or module.startswith("findata.")
    ]
    assert violations == []


def test_contracts_remain_independent():
    violations = [
        (str(file.relative_to(ROOT)), module)
        for file, module in _imports_under(ROOT / "packages" / "optifolio_contracts")
        if module == "src" or module.startswith("src.") or module == "findata" or module.startswith("findata.")
    ]
    assert violations == []

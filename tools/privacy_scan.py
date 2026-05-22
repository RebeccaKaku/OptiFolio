"""Scan the repository for business-private files and likely private values."""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List


BLOCKED_EXACT_PATHS = {
    "config/portfolio.yaml",
    "config/secrets.yaml",
}

BLOCKED_PREFIXES = (
    "data/",
    "local/",
)

PATH_ALLOWLIST = {
    "local/README.md",
}

BLOCKED_SUFFIXES = (
    ".parquet",
    ".db",
    ".db-journal",
    ".sqlite",
    ".sqlite3",
    ".csv",
    ".xlsx",
)

CONTENT_RULES = [
    (
        "portfolio_snapshot",
        re.compile(r"(?im)^(cash|positions)\s*:\s*$"),
        "cash/positions YAML blocks should only appear in approved templates or tests",
    ),
    (
        "credential_field",
        re.compile(r"(?i)(api[_-]?key|secret[_-]?key|password|access[_-]?token|account[_-]?id)\s*[:=]\s*[\"']?[^\"'\s#]+"),
        "credential-looking assignment",
    ),
    (
        "broker_account",
        re.compile(r"(?i)\b(broker\s*:|account[_-]?id\s*[:=]|client[_-]?id\s*[:=])"),
        "broker/account wording may indicate private settings",
    ),
]

CONTENT_ALLOWLIST = (
    "config/portfolio.example.yaml",
    "config/secrets.example.yaml",
    "docs/",
    "tests/",
    "tools/privacy_scan.py",
)


@dataclass
class Finding:
    severity: str
    rule: str
    path: str
    line: int | None
    message: str

    def format(self) -> str:
        location = self.path if self.line is None else f"{self.path}:{self.line}"
        return f"[{self.severity}] {self.rule} {location} - {self.message}"


def run_git(args: List[str], cwd: Path) -> List[str]:
    result = subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def iter_candidate_paths(cwd: Path) -> Iterable[str]:
    tracked = run_git(["ls-files"], cwd)
    untracked = run_git(["ls-files", "--others", "--exclude-standard"], cwd)
    return sorted(set(tracked + untracked))


def normalize(path: str) -> str:
    return path.replace(os.sep, "/")


def is_binary_or_large(path: Path) -> bool:
    try:
        if path.stat().st_size > 2_000_000:
            return True
        with path.open("rb") as fh:
            chunk = fh.read(2048)
        return b"\0" in chunk
    except OSError:
        return True


def path_findings(paths: Iterable[str]) -> List[Finding]:
    findings: List[Finding] = []
    for raw_path in paths:
        path = normalize(raw_path)
        if path in PATH_ALLOWLIST:
            continue
        if path in BLOCKED_EXACT_PATHS:
            findings.append(
                Finding("BLOCK", "blocked_path", path, None, "private config must not be tracked")
            )
        if path.startswith(BLOCKED_PREFIXES):
            findings.append(
                Finding("BLOCK", "blocked_directory", path, None, "private/local data directory")
            )
        if path.lower().endswith(BLOCKED_SUFFIXES):
            findings.append(
                Finding("BLOCK", "blocked_file_type", path, None, "runtime data file type")
            )
    return findings


def content_allowed(path: str) -> bool:
    return path.startswith(CONTENT_ALLOWLIST) or path in CONTENT_ALLOWLIST


def content_findings(cwd: Path, paths: Iterable[str]) -> List[Finding]:
    findings: List[Finding] = []
    for raw_path in paths:
        path = normalize(raw_path)
        full_path = cwd / raw_path
        if not full_path.is_file() or content_allowed(path) or is_binary_or_large(full_path):
            continue
        try:
            lines = full_path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue

        for index, line in enumerate(lines, start=1):
            for rule_name, pattern, message in CONTENT_RULES:
                if pattern.search(line):
                    findings.append(Finding("WARN", rule_name, path, index, message))
    return findings


def run_detect_secrets(cwd: Path) -> int:
    result = subprocess.run(
        [sys.executable, "-m", "detect_secrets", "scan", "--all-files"],
        cwd=str(cwd),
        text=True,
    )
    return result.returncode


def main() -> int:
    parser = argparse.ArgumentParser(description="Scan for private business data.")
    parser.add_argument("--strict", action="store_true", help="Treat warnings as failures.")
    parser.add_argument(
        "--with-detect-secrets",
        action="store_true",
        help="Also run detect-secrets if installed.",
    )
    args = parser.parse_args()

    cwd = Path.cwd()
    paths = list(iter_candidate_paths(cwd))
    findings = path_findings(paths) + content_findings(cwd, paths)

    for finding in findings:
        print(finding.format())

    blockers = [finding for finding in findings if finding.severity == "BLOCK"]
    warnings = [finding for finding in findings if finding.severity == "WARN"]

    if args.with_detect_secrets:
        detect_status = run_detect_secrets(cwd)
        if detect_status != 0:
            print("[WARN] detect_secrets unavailable or returned a non-zero status")

    print(
        f"Privacy scan complete: {len(blockers)} blocker(s), "
        f"{len(warnings)} warning(s), {len(paths)} file(s) checked."
    )

    if blockers or (args.strict and warnings):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

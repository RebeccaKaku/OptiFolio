## Problem

After the FinData directory restructure (fetcher_dept to adapters, orchestrator to orchestration), 8 tests fail. They fall into 2 root causes.

## Root Cause 1: Orchestrator dispatch tests (6 failures)

Files: tests/test_findata_orchestrator.py
Classes: TestOrchestratorDispatch, TestOrchestratorEndToEnd
Failures: test_dispatch_empty_tasks, test_dispatch_logs_failures, test_dispatch_with_real_fetcher_and_store, test_full_scan_on_empty_store, test_dispatch_success_path, test_dispatch_fallback_on_quality_rejection

Likely cause: The Orchestrator class in FinData/orchestration/orchestrator.py uses lazy imports (runtime from FinData.orchestrator... import ...) that reference the old module paths (orchestrator). These were renamed to orchestration. Search for and fix any lazy/runtime import strings inside FinData/orchestration/ that still say "orchestrator" instead of "orchestration".

## Root Cause 2: cn_fund adapter constraint tests (2 failures)

Files: tests/test_findata_fetcher.py
Class: TestThinAdapterConstraints
Failures: test_no_empty_check_in_adapter and test_no_file_writes_in_adapter

Cause: FinData/adapters/cn_fund.py was merged from a thin adapter + backend implementation during restructuring. It now contains the full implementation including .empty checks and file writes. The constraint tests expect a pure adapter pattern. Fix: update the two failing tests to accept the merged implementation.

## Test Command

C:\Users\Z\miniconda3\envs\optifolio313\python.exe -m pytest tests/ -q --tb=line

## Rules

- Do NOT rename directories back to old names
- Do NOT delete test files
- All 582 existing passing tests must remain passing
- Make small, focused PRs

# OptiFolio Documentation Index

**Last updated**: 2026-06-05

This index points to the current docs first. Older Streamlit-era documents remain available for context, but they should not be treated as the implementation source of truth.

---

## Start Here

| Document | Purpose |
|---|---|
| [Current State And Code Review](CURRENT_STATE_2026-06-05.md) | Live project status, risks, standard test command, near-term and long-term roadmap. |
| [Financial Logic And Module Design](FINANCIAL_LOGIC_AND_MODULE_DESIGN.md) | Top-level financial domain model, data contracts, algorithm interfaces, naming refactor, and AI-sized task slices. |
| [Phase 0 Protection And Refactor Plan](PHASE0_AND_REFACTOR_PLAN.md) | Migration strategy from Streamlit-first app to FastAPI/services/frontend. |
| [Time Alignment Design](TIME_ALIGNMENT_DESIGN.md) | Critical design for cross-market valuation and look-ahead-bias prevention. |
| [AI Context](AI_CONTEXT.md) | Handoff context for AI coding agents. |

## Developer Guides

| Document | Purpose |
|---|---|
| [Quick Development Guide](快速开发指南.md) | Short local-development guide. Some sections may still be legacy-oriented. |
| [Development Guide](开发指南.md) | Broader development notes and conventions. |
| [Architecture Foundation](ARCHITECTURE_FOUNDATION.md) | Current architecture foundation notes. |
| [System Architecture Design](系统架构设计文档.md) | Older architecture design document. Use with the current-state doc. |
| [Asset Import Guide](资产导入使用指南.md) | Asset import workflow and registry details. |

## Data And Fetcher Notes

| Document | Purpose |
|---|---|
| [Fetcher Quality Analysis](FETCHER_QUALITY_ANALYSIS.md) | Fetcher quality notes and follow-ups. |
| [AKShare Friction API Survey](AKSHARE_FRICTION_API_SURVEY.md) | Fund fee/friction API investigation. |
| [BOC Data Investigation](boc_data_investigation_report.md) | BOC wealth-management data investigation. |
| [Network Interface Tests](网络接口测试.md) | Network/API connectivity notes. |

## Review And Handoff Notes

| Document | Purpose |
|---|---|
| [Jules PR Review 2026-05-22](JULES_PR_REVIEW_2026-05-22.md) | Prior PR review notes for bank fetchers. |
| [Jules Cloud Tasks](JULES_CLOUD_TASKS.md) | Prior cloud-task ledger. |
| [DeepSeek To Codex](DEEPSEEK_TO_CODEX.md) | Handoff notes from earlier work. |
| [Debug Handoff DeepSeek](DEBUG_HANDOFF_DEEPSEEK.md) | Debug handoff notes. |
| [Financial Expert Review](FINANCIAL_EXPERT_REVIEW.md) | Financial-domain review notes. |

## Legacy Or Stale Docs

These files are retained for history, but current decisions should be checked against [Current State And Code Review](CURRENT_STATE_2026-06-05.md):

- `代码审查与改进建议.md` - 2026-02 Streamlit-era review.
- `最终完成报告.md` - historical completion report.
- `改进总结.md` - historical improvement summary.
- `USER_GUIDE.md` - may describe older UI behavior.
- `运行流程文档.md` - may describe older run paths.

---

## Current Local Commands

Start the API:

```powershell
python tools/start_app.py
```

Run the reliable test command on this Windows workspace:

```powershell
python -m pytest tests -q --basetemp .pytest_tmp -p no:cacheprovider
```

Run privacy scan before publishing:

```powershell
python tools/privacy_scan.py --strict --with-detect-secrets
```

## Current Implementation Source Of Truth

- API entrypoint: `src/api/fastapi_app.py`
- Service graph: `src/services/application.py`
- Date-aware valuation: `src/core/valuation.py`
- Portfolio V2 service: `src/services/portfolio_service_v2.py`
- Canonical market data: `src/data_foundation/`
- Legacy dashboard: `app.py`

New feature work should use FastAPI/services/core paths. Do not add new product behavior to `app.py` unless the task is explicitly a legacy dashboard compatibility fix.

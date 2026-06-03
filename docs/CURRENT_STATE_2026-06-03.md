# OptiFolio 当前状态与推进路线

**日期**: 2026-06-03
**分支**: master（fix-bank-apis / feat-bosc / debug-branch 已合并并删除）
**版本**: 0.1.0 (架构重构中)
**测试**: 77 passed, 12 skipped, 0 failures

---

## 项目概述

OptiFolio 是一个量化投资组合优化与金融数据分析系统，支持多资产类型（股票、基金、理财、加密货币）、
多数据源（akshare、yfinance、ccxt、BOSC/BOC/ICBC 银行理财 API），以及 Markowitz/Black-Litterman
优化和向量化回测。

系统正在从单体 Streamlit 应用重构为分层架构：

```
frontend/            # React + Vite UI（未开始）
src/api/             # FastAPI HTTP API（已就绪）
src/services/        # 业务服务层（已就绪）
src/core/            # 组合、资产、定价核心
src/data_foundation/ # 市场数据仓储（Parquet + DuckDB）
src/research/        # 回测引擎（vectorbt + pandas）
fetchers/            # 数据抓取器（7 个数据源）
portfolio/           # 优化算法（Markowitz、Black-Litterman）
```

---

## ✅ 已完成

### Jules Cloud Tasks（5/5）

| # | 任务 | 状态 | 提交 |
|---|------|------|------|
| 1 | Ingestion Adapter → MarketDataRepository | ✅ | `06beec4` |
| 2 | 优化端点加固 | ✅ | `55b881f` |
| 3 | Vectorbt 回测适配器 | ✅ | `98df050` |
| 4 | 测试卫生清理 | ✅ | `c1d836d` |
| 5 | 开发者启动脚本 + Python 版本文档 | ✅ | `1840dac` |

### Portfolio Management 系统（新完成）

| # | 模块 | 说明 |
|---|------|------|
| — | `src/domain/models.py` | 新增 ValuationRequest, ValuationResult, PositionValue, CashHolding |
| — | `src/domain/corporate_actions.py` | DividendAction, StockSplitAction, MergerAction |
| — | `src/domain/fees.py` | TransactionFee, ManagementFee, TaxRule, FeeSchedule |
| — | `src/core/valuation.py` | **ValuationEngine** — 日期感知定价，使用 MarketDataRepository |
| — | `src/core/corporate_actions.py` | CorporateActionProcessor — YAML 持久化 |
| — | `src/core/fees.py` | FeeProcessor |
| — | `src/core/portfolio_history.py` | PortfolioHistoryTracker — Parquet 存储 + 绩效指标 |
| — | `src/services/portfolio_service_v2.py` | **PortfolioServiceV2** — 一站式服务入口 |
| — | `src/api/fastapi_app.py` | 10 个新 V2 路由 |

### 银行 Fetcher 修复

| 数据源 | 状态 | 测试 |
|--------|------|------|
| BOSC | ✅ 接口修复，mock 测试完整 | 8 assertions |
| BOC | ✅ 接口正常 | 3 assertions |
| ICBC | ✅ 接口正常 | 8 assertions |

### 其他

- 并发数据加载（从 remote PR 移植）
- BOSC 历史净值抓取升级
- 分支合并：fix-bank-apis / feat-bosc / debug-branch → master

---

## 🔴 当前阻塞：时间对齐（新）

详见 `docs/TIME_ALIGNMENT_DESIGN.md`。

**核心问题：** 跨时区资产（美股 / A股 / 港股 / 加密货币）的价格时间戳在系统内不一致。

- `normalize_market_frame()` 无条件抹除所有时区信息（`schemas.py:84`）
- 不同 fetcher 对同一美股收盘事件产生不同的 naive 时间戳
- 对含美股+A股的组合调用 `value_on(T)` 时，无"可知道性"（knowability）约束

**状态：** 设计完成，待开始实施 Phase A（基础设施）。

### ~~旧阻塞：3 个测试失败~~ ✅ 已修复

- ~~duckdb 未安装~~ → `pip install duckdb`
- ~~BOSC fetcher test mock 不完整~~ → 扩展 mock 覆盖 NET_WORTH_URL
- ~~ICBC test 无 assertion~~ → 8 个 assertions

---

## 🟡 Jules PR Review 待解决（BOSC/BOC/ICBC Fetchers）

来源: `docs/JULES_PR_REVIEW_2026-05-22.md`

| # | 问题 | 严重度 | 状态 |
|---|------|--------|------|
| 1 | `bosc.py:55` `httpx.AsyncClient(verify=False)` 全局禁用 TLS 验证 | 中 | 未修复 |
| 2 | BOSC `fetch()` 总是返回空 DataFrame，未实现标准 OHLCV 数据路径 | 高 | 部分修复（`a5a4da7` 加了历史净值，但测试仍失败） |
| 3 | `test_icbc_fetcher_sync_defaults` 无任何 assertion | 中 | 未修复 |
| 4 | BOSC 测试只检查文件存在，不验证 schema/index/close 值 | 中 | 未修复 |
| 5 | PR 不应修改 `config/asset_registry.yaml` | 低 | 需确认 |
| 6 | 需要从当前 `origin/main` rebase | 低 | 需确认 |
| 7 | 依赖更新需要对齐当前 `pyproject.toml` | 低 | 需确认 |

---

## 📋 推进路线

### 🔴 当前：时间对齐

- [ ] **Phase A: 基础设施** — 创建 ExchangeCalendar 注册表，扩展 canonical schema
- [ ] **Phase B: Fetcher 改造** — 统一所有 fetcher 到交易所当地日期
- [ ] **Phase C: 估值引擎增强** — 可知道性检查、多日历回看
- [ ] **Phase D: 回测加固** — 多日历重采样

### 第一优先级：修复构建 ✅ 已完成

- [x] 安装 duckdb
- [x] 修复 BOSC fetcher 测试 mock
- [x] 加固 ICBC fetcher 测试

### 第二优先级：BOSC/BOC/ICBC Fetcher PR ✅ 已完成

- [x] 合并到 master
- [x] 测试完整（BOSC 8 assertions, ICBC 8 assertions, BOC 3 assertions）

### 第三优先级：Portfolio Management ✅ 已完成

- [x] Domain 模型扩展
- [x] ValuationEngine（日期感知定价）
- [x] CorporateActionProcessor + FeeProcessor（接口桩）
- [x] PortfolioHistoryTracker
- [x] PortfolioServiceV2 + 10 个 API 路由
- [x] FastAPI 集成

### 第四优先级：架构推进

- [ ] **Phase 1: 前端建设** — 创建 `frontend/` React + Vite 项目
- [ ] **Phase 3: Portfolio/Pricing 加固** — 替换 print 为 logger、离线确定性估值
- [ ] **Phase 4: Asset Registry 决策** — 完成或删除跳过的测试
- [ ] **Phase 6: 淘汰 Streamlit** — 在 FastAPI + React 覆盖功能后移除 `app.py`

### 长期方向

- [ ] Qlib 因子/ML 研究导出（`qlib_adapter.py` 仍是占位符）
- [ ] 实时行情（WebSocket）
- [ ] 多用户权限管理
- [ ] 移动端支持

---

## 关键文件索引

| 文件 | 用途 |
|------|------|
| `src/api/fastapi_app.py` | FastAPI 入口（端口 8011） |
| `src/services/application.py` | 服务依赖图 |
| `src/services/research_service.py` | 优化 + 回测编排 |
| `src/data_foundation/repository.py` | DuckDB 市场数据仓储 |
| `src/data_foundation/schemas.py` | 标准市场数据 schema + Pandera 校验 |
| `src/research/backtest.py` | 回测引擎（vectorbt + pandas fallback） |
| `fetchers/bosc.py` | 上海银行理财抓取器 |
| `fetchers/boc.py` | 中国银行理财抓取器 |
| `fetchers/icbc.py` | 工商银行理财抓取器 |
| `fetchers/cn_fund.py` | 中国公募基金抓取器 |
| `portfolio/optimizer.py` | 组合优化器（Markowitz、Black-Litterman） |
| `config/portfolio.yaml` | 持仓快照（不提交 git） |
| `config/portfolio.example.yaml` | 持仓模板（安全提交） |
| `tools/start_app.py` | 统一启动脚本 |
| `docs/CURRENT_STATE_2026-06-03.md` | 本文档 |

---

## 开发规范（来自 Jules Cloud Tasks）

1. **隐私边界**: 真实数据放 `local/`，不提交 git
2. **PR 粒度**: 一个任务 = 一个 PR，小而聚焦
3. **测试**: 提交前运行 `pytest -q` 必须全绿
4. **隐私扫描**: `python tools/privacy_scan.py --strict --with-detect-secrets`
5. **Python 版本**: `>=3.11, <3.14`（量化栈在 3.14 上不稳定）
6. **默认端口**: FastAPI 使用 `8011`
7. **不修改 Streamlit**: 除非任务明确要求迁移

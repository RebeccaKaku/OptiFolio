# OptiFolio 当前状态与推进路线

**日期**: 2026-06-03
**分支**: master
**版本**: 0.1.0 (架构重构中)

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

### Jules Cloud Tasks（5/5 全部完成）

| # | 任务 | 状态 | 提交 |
|---|------|------|------|
| 1 | Ingestion Adapter → MarketDataRepository | ✅ | `06beec4` |
| 2 | 优化端点加固（参数校验、错误处理） | ✅ | `55b881f` |
| 3 | Vectorbt 回测适配器 | ✅ | `98df050` |
| 4 | 测试卫生清理 | ✅ | `c1d836d` |
| 5 | 开发者启动脚本 + Python 版本文档 | ✅ | `1840dac` |

### 额外完成

- 并发数据加载（从 remote PR 移植）: `9e1e591`
- BOSC 历史净值抓取升级: `a5a4da7`
- BOSC 净值日期解析修复: `d03c314`
- CORS 安全修复 + 重复代码清理: `e785b07`
- 模块化架构重构: `5797f67`

---

## 🔴 当前阻塞：3 个测试失败

运行 `python -m pytest tests/ -q` 的结果：

```
FAILED tests/test_data_foundation.py — duckdb module missing
FAILED tests/test_fetchers.py::test_bosc_fetcher_sync — BOSC fetch 返回空 DataFrame
FAILED tests/test_ingestion_adapter.py — duckdb module missing
43 passed, 12 skipped, 3 failed
```

### 根因

| 失败 | 原因 | 修复方案 |
|------|------|----------|
| `test_data_foundation.py` | `duckdb` 包未安装在当前环境 | `pip install duckdb` |
| `test_ingestion_adapter.py` | 同上 | 同上 |
| `test_bosc_fetcher_sync` | Mock 只覆盖了产品发现 API（`PRODUCT_LIST_URL`），未覆盖净值历史 API（`NET_WORTH_URL`），导致 `fetch()` 返回空 DataFrame | 扩展 mock，为 `NET_WORTH_URL` 的 POST 请求返回 `{"dates": [...], "rates": [...]}` |

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

### 第一优先级：修复构建（目标：全部测试通过）

- [ ] **安装 duckdb**: `pip install duckdb`
- [ ] **修复 BOSC fetcher 测试 mock**: 为 `NET_WORTH_URL` 添加 mock 返回
- [ ] **加固 ICBC fetcher 测试**: 添加有意义的 assertion

### 第二优先级：完成 BOSC/BOC/ICBC Fetcher PR

- [ ] 将 `verify=False` 改为可配置参数，添加注释说明原因
- [ ] 确认 BOSC `fetch()` 返回标准 OHLCV DataFrame
- [ ] 强化测试：验证 DataFrame schema、index 类型、close 值、空数据/错误场景
- [ ] 确保不修改共享 config 文件
- [ ] 从当前 `origin/main` rebase，重新提交 PR

### 第三优先级：架构推进

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

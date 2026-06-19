# Personal Book 第一批验收报告

**日期**：2026-06-19

**范围**：DS-001 至 DS-006C 及合并后的 `PortfolioBookDatabase` schema v7

**结论**：后端地基验收通过；五项加固问题均已关闭，可以开始 DS-007。

## 已实现

- 本地 SQLite 数据库和顺序 schema migration；
- 账户创建、查询、更新和停用；
- 产品定义持久化与扩展字段往返；
- `draft/confirmed/superseded` 快照批次；
- 持仓快照；
- 现金流事件和转账关联；
- 数据库备份、验证和恢复；
- 所有真实数据默认位于 `local/`，与 FinData 分离。

## 验证结果与证据

- DS-006A 当时 Personal Book 专项：`77 passed`，全量：`731 passed, 2 warnings`；
- 此后 DS-006B/DS-006C 和多项仓库清理已进入主分支；旧测试数字仅作为历史证据，当前总数以 fresh run 和 `docs/AI_CONTEXT.md` 为准；
- 关闭提交：DS-006A `d614b19`、DS-006B `1dd037a`、DS-006C `eef07e7`；
- 全量测试需要在当前受管环境设置 `NUMBA_DISABLE_JIT=1`，否则 vectorbt/Numba 在收集阶段尝试创建不可用缓存；
- 基础隐私扫描：`0 blocker(s)`；48 条 warning 均为 `account_id`、GitHub secret 表达式等启发式命中，需要后续单独降噪；
- `detect-secrets` 当前环境未安装，因此带 `--with-detect-secrets` 的增强扫描未完成。

## 本轮已清理

- 增加 `.pytest_tmp*/`、`.playwright-mcp/` 和 `*.parquet.lock` 忽略规则；
- 从 Git 索引移除 155 个误提交的 pytest 临时数据库/指针文件；
- 从 Git 索引移除 `data/foundation/market_prices.parquet.lock`；
- 删除工作区内本轮及旧的 pytest 临时目录；
- 撤销测试运行对 `config/asset_registry.yaml` 造成的纯时间戳漂移；
- 为 `update_account()` 增加字段白名单、基本输入校验和不存在账户检查。

## 历史发现及关闭情况

### 1. 快照不能表达账户覆盖范围 — 已关闭

当前批次只保存实际持仓行。若某账户本次没有录入，系统无法区分：

- 该账户本次尚未录；
- 该账户已录完且余额为零；
- 本次只录了部分产品。

DS-006A 已新增批次—账户 coverage，区分 complete/partial/empty，并明确完整度。

### 2. 银行理财快照强制要求 quantity — 已关闭

DS-006A 已允许 quantity 可空，并强制 quantity 与 market value 至少一项存在。

### 3. 现金流符号与财富含义不明确 — 已关闭

当前实现允许 subscription/redemption 等类型，但没有统一说明 `amount` 是现金账户变化、产品交易金额还是外部资金流。后续对账最关心的是“是否改变个人净资产”：

- 外部注资/取出改变可比本金；
- 内部转账、换汇、申购赎回不改变个人净资产；
- 利息、分红和费用属于投资结果。

DS-006B 已固定事件类型、正负号、财富分类、换汇和内部转账配对规则。

### 4. 备份验证还不够强 — 已关闭

DS-006C 已加入 SQLite integrity check、源文件存在性检查和原子恢复/回滚保护。

### 5. schema v5 没有显式 migration — 已关闭

DS-006A 已加入显式 v5 兼容迁移；v6 为 snapshot coverage，v7 为 cashflow/backup 加固后的当前版本。

## 里程碑判断

- DS-001 至 DS-006C：完成，地基关闭；
- M0“停止打转”：完成；
- M1“可中断的个人建账”：尚未完成，因为还没有 API、录入界面、逐账户进度和 OCR 草稿边界；
- 下一条用户可见主线是：账户/产品 API → 快照 API → 最小建账界面 → 截图草稿边界。

## 下一期顺序

1. DS-007 已实现并通过 Codex 审查（专项 222、全量 869 项通过），等待提交；
2. 恢复后的下一项：`DS-008_snapshot_draft_confirm_api.md`；
3. 然后：`DS-009_minimal_onboarding_ui.md`；
4. 最后：`DS-010_screenshot_import_draft_contract.md`。

共同执行规则见 `plans/deepseek/README.md`。一次只实现一个任务，由 Codex 审查通过后再进入下一项。

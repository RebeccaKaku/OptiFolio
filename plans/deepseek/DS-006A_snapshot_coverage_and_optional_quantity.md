# DS-006A：快照覆盖范围与可选份额

**状态**：2026-06-19 已完成，经 Codex 补充迁移回填与数据库约束后，专项 77 项、全量 731 项测试通过。

本任务是 Personal Book 地基验收任务。只完成本文件要求，不开始 API 或 UI。

## 用户价值

用户可能分几天录入不同银行，也可能只看到理财市值而没有份额。系统必须区分“没有录”“已经录完且为空”“只录了一部分”，并允许只录报告市值。

## 依赖

- 当前主分支已完成 DS-001 至 DS-006；
- 阅读 `docs/PORTFOLIO_BOOK_PHASE1_AUDIT_2026-06-19.md`；
- 本任务完成后 schema version 应为 6。

## 允许修改

- `src/core/portfolio_book_db.py`
- `tests/test_portfolio_book_db.py`

## 禁止修改

- `FinData/`
- `src/api/`
- `src/services/`
- `app.py`
- `config/asset_registry.yaml`
- `local/`
- 其他业务模块和文档

## 任务一：显式说明 schema v5

当前代码版本为 v5，但 migration map 只有 v1-v4。新增显式 `_migrate_v5()`，说明它是合并 snapshot 与 cashflow 分支后的无结构变化兼容标记，并把它注册到 migration map。不得悄悄跳过版本。

## 任务二：新增批次账户覆盖表

schema v6 新增 `snapshot_batch_accounts`：

```text
batch_id       FK -> snapshot_batches
account_id     FK -> accounts
coverage       complete | partial | empty
notes          nullable
PRIMARY KEY(batch_id, account_id)
```

金融语义：

- `complete`：该账户在本次 `as_of` 已完整录入；
- `partial`：只录入了部分产品，不能用于完整账户收益；
- `empty`：已确认该账户当日无余额/持仓，不等于“没有录”。

新增最小方法：

```python
set_batch_account_coverage(batch_id, account_id, coverage, notes=None)
get_batch_progress(batch_id) -> dict
```

要求：

- 仅 draft 批次可修改覆盖状态；
- coverage 必须严格校验；
- `get_batch()` 返回覆盖信息；
- position snapshot 的 account_id 必须已登记在该批次覆盖表中；
- `empty` 账户不得含持仓；
- 确认批次前至少登记一个账户；
- `partial` 批次可以确认，但进度结果必须明确 `is_complete=False`；
- 所有登记账户均为 complete/empty 时才 `is_complete=True`。

## 任务三：quantity 改为可选

使用可回滚的 v6 migration 重建 `position_snapshots`，将 `quantity` 改为 nullable，同时完整保留旧数据、唯一约束和外键。

`add_snapshot()` 规则：

- `quantity` 与 `market_value` 至少一个非空；
- 二者均为空时拒绝；
- quantity、market_value、cost_basis 不得为负；
- 零值合法，例如确认空仓前最后的零余额记录，但一般空账户优先使用 coverage=`empty`；
- 不得用 0 冒充未知值。

## 明确非目标

- 不设计现金流符号；
- 不修改金额存储精度；
- 不新增 API、service 或 UI；
- 不迁移 YAML；
- 不重构整个数据库类。

## 必须新增的测试

- 从全新数据库初始化到 v6；
- 从真实 v5 fixture 迁移到 v6，旧快照无损；
- 显式 v5 migration 可执行；
- quantity=None + market_value 有值可以保存；
- quantity 和 market_value 同时为空被拒绝；
- 负数被拒绝；
- 未登记账户覆盖时不能加持仓；
- empty 账户不能加持仓；
- confirmed 批次不能修改覆盖；
- partial 进度不是完整；
- complete + empty 组合可被判定完整；
- 无任何账户的批次不能确认。

## 验证

```powershell
python -m pytest tests/test_portfolio_book_db.py -q --basetemp .pytest_tmp_ds006a -p no:cacheprovider
```

不得提交 `.pytest_tmp*`、数据库文件或资产注册表时间戳变化。

## 最终汇报

列出 migration 行为、覆盖状态语义、测试结果、刻意未做事项和任何兼容风险。

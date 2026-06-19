# Personal Book 第一批验收报告

**日期**：2026-06-19

**范围**：DS-001 至 DS-006 及合并后的 `PortfolioBookDatabase`

**结论**：后端地基有条件通过；在开放 API 前必须完成 DS-006A、DS-006B、DS-006C。

## 已实现

- 本地 SQLite 数据库和顺序 schema migration；
- 账户创建、查询、更新和停用；
- 产品定义持久化与扩展字段往返；
- `draft/confirmed/superseded` 快照批次；
- 持仓快照；
- 现金流事件和转账关联；
- 数据库备份、验证和恢复；
- 所有真实数据默认位于 `local/`，与 FinData 分离。

## 验证结果

- Personal Book 专项：`54 passed`；
- 全量测试：`708 passed, 2 warnings`；
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

## 为什么只是“有条件通过”

### 1. 快照不能表达账户覆盖范围

当前批次只保存实际持仓行。若某账户本次没有录入，系统无法区分：

- 该账户本次尚未录；
- 该账户已录完且余额为零；
- 本次只录了部分产品。

这会破坏“可中断建账”和后续收益计算。DS-006A 必须增加批次—账户覆盖记录。

### 2. 银行理财快照强制要求 quantity

`position_snapshots.quantity` 当前为 `NOT NULL`，但银行 App 经常只展示报告市值，不提供可用份额。真实需求要求 quantity 和 market value 至少一个存在，而不是强制 quantity。

### 3. 现金流符号与财富含义不明确

当前实现允许 subscription/redemption 等类型，但没有统一说明 `amount` 是现金账户变化、产品交易金额还是外部资金流。后续对账最关心的是“是否改变个人净资产”：

- 外部注资/取出改变可比本金；
- 内部转账、换汇、申购赎回不改变个人净资产；
- 利息、分红和费用属于投资结果。

DS-006B 必须先固定事件类型、正负号和配对规则。

### 4. 备份验证还不够强

当前 `verify_backup()` 只验证能否读取 schema version，未执行 SQLite integrity check；备份源不存在时也可能被连接动作创建为空文件。DS-006C 必须完善完整性和原子恢复。

### 5. schema v5 没有显式 migration

当前 migration 表只列出 v1-v4，但代码版本为 v5。虽然新库最终结构可用，这种隐式“空版本”会让将来的维护者无法判断 v5 是合并标记还是漏写迁移。DS-006A 需要显式记录。

## 里程碑判断

- DS-001 至 DS-006：代码已合并，等待加固后最终关闭；
- M0“停止打转”：完成；
- M1“可中断的个人建账”：尚未完成，因为还没有 API、录入界面、逐账户进度和 OCR 草稿边界；
- 下一条用户可见主线仍是：地基加固 → API → 最小建账界面。

## 下一期顺序

1. `DS-006A_snapshot_coverage_and_optional_quantity.md`
2. `DS-006B_cashflow_semantics.md`
3. `DS-006C_backup_integrity.md`
4. 通过统一验收后，再开始 DS-007、DS-008、DS-009。

这三个任务修改同一核心模块，必须顺序执行，不要并行合并。

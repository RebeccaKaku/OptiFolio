# DS-006B：现金流金融语义与配对规则

本任务在 DS-006A 合并后执行。不要与 DS-006A 并行。

## 用户价值

后续收益归因必须区分“投资赚亏”和“用户新放进或拿走的钱”。本任务固定现金流的金融含义，避免 API 和对账引擎各自猜测。

## 依赖

- DS-006A 已合并；
- 起始 schema version 为 6；
- 完成后 schema version 为 7。

## 允许修改

- `src/core/portfolio_book_db.py`
- `tests/test_portfolio_book_db.py`

## 禁止修改

- API、service、UI、FinData、local、资产注册表和其他业务模块。

## 唯一金额符号约定

`amount` 表示事件对该账户该币种现金的变化：

- 正数：现金增加；
- 负数：现金减少；
- 不允许 0。

合法事件及要求：

```text
external_contribution  正数   外部资金进入个人资产
external_withdrawal    负数   资金离开个人资产
purchase               负数   购买产品，内部配置变化
sale                   正数   赎回/卖出产品，内部配置变化
interest               正数   投资收益
dividend               正数   投资收益
fee                    负数   投资损失/成本
tax                    负数   投资损失/成本
transfer_in            正数   账户间转入，必须与 transfer_out 配对
transfer_out           负数   账户间转出，必须与 transfer_in 配对
fx_conversion          amount<0 且 counter_amount>0，币种必须不同
maturity               正数   到期回款
other                  非零   notes 必填，后续默认不可自动归因
```

旧值迁移：

- `subscription` → `purchase`；
- `redemption` → `sale`；
- 无法满足新符号约定的旧测试数据必须在 migration 测试中明确处理，不得静默翻转真实金额。

## schema v7

重建 `cashflow_events` 以补充：

- `product_id` 外键到 products；
- 必要的 CHECK 约束；
- 保留现有数据和时间字段；
- 对 transfer pair 是否使用自引用外键由实现决定，但不得破坏先创建两腿、后配对的工作流。

## link_transfer() 规则

- 两个事件必须存在；
- 必须一条 transfer_out、一条 transfer_in；
- 币种相同；
- 绝对金额相同；
- 不能与自己配对；
- 已与第三条事件配对时拒绝；
- 两条更新必须在同一事务中完成；
- 任一检查失败不得留下半配对状态。

新增一个纯函数或方法，用于返回事件财富分类：

```text
external_flow   external_contribution / external_withdrawal
investment_pnl  interest / dividend / fee / tax
internal        purchase / sale / transfer / fx_conversion / maturity
unclassified    other
```

注意：`maturity` 通常是本金回到现金，不应自动算收益；若包含利息，应另记 interest 或等待对账拆分。

## 明确非目标

- 不实现最终对账引擎；
- 不计算收益率；
- 不新增 API；
- 不把产品市值变化写成现金流；
- 不为兼容错误语义保留别名接口。

## 必须新增的测试

- 每种事件的正确符号通过、错误符号拒绝；
- 0 金额拒绝；
- FX 两币种、两金额及不同币种校验；
- product 外键生效；
- 转账合法配对；
- 不存在、同向、金额不同、币种不同、自配对、重复配对全部拒绝；
- 失败后两腿均保持未配对；
- v6 → v7 migration 保留并转换合法旧事件；
- 财富分类结果正确。

## 验证

```powershell
python -m pytest tests/test_portfolio_book_db.py -q --basetemp .pytest_tmp_ds006b -p no:cacheprovider
```

不得提交任何 `.pytest_tmp*`、SQLite 文件或真实金额。

# DS-011：快照对账引擎

**用户价值**：两次不连续录入之间，区分现金流、投资变化和无法解释的差额。  
**依赖**：DS-010；当前 schema v8，沿用 v7 引入的 cashflow 语义。

## 允许修改

- 新增 `src/analytics/reconciliation.py`
- 新增 `tests/test_analytics_reconciliation.py`

禁止数据库、API、UI、估值抓取和修改既有 analytics。

## 纯函数契约

定义不可变输入/输出 dataclass：

- `PositionInput(account_id,product_id,quantity?,market_value?,cost_basis?,currency,source?,quality?)`；
- `SnapshotInput(batch_id,as_of,status,account_coverage,positions,cashflow_coverage)`，coverage 为 account_id→complete/partial/empty；cashflow_coverage=`complete|partial|unknown`；
- `CashflowInput(event_id,event_type,account_id,product_id?,amount,currency,counter_amount?,counter_currency?,pair_event_id?,effective_date)`，字段语义完全沿用 schema v7；
- `ReconciliationResult` 的所有金额使用 Decimal，提供显式 JSON 字符串序列化，不在纯计算中舍入。

输入是同一范围的期初/期末 confirmed snapshot、期间 cashflows、账户 coverage。输出至少包含：

`opening_value, closing_value, external_net_flow, investment_income, fees_taxes, market_change, internal_flow_net, explained_change, unclassified_change, coverage_status, is_return_eligible, warnings`。

恒等式（同币种、同估值口径）：

`closing - opening = external_net_flow + investment_income + fees_taxes + market_change + unclassified_change`，其中 `explained_change=external_net_flow+investment_income+fees_taxes+market_change`。

purchase/sale/transfer/fx 的内部本金移动不直接计入收益；配对内部转账总和为 0。maturity 中本金部分属于内部回收，只有明确拆出的利息才属于 investment income；无法拆分则进入 unclassified。只有 cashflow_coverage=complete 且两端完整时，扣除已分类流量后的 residual 才可命名为 market_change；否则必须进入 unclassified_change。

## 完整度规则

只有期初、期末相关账户均 complete/empty，币种和估值口径一致，且关键现金流可分类时 `is_return_eligible=True`。partial/missing 时仍可输出已知金额，但禁止全组合收益率。

## 精度与日期

使用 Decimal；现金流区间采用 `(opening_as_of, closing_as_of]` 并在代码注释固定。日期倒序、同日重复 confirmed 批次、币种混合未折算均返回明确错误。

## 必须测试

纯市场变化、外部入金、费用、利息、买卖、配对转账、换汇、缺现金流形成 unknown、partial 禁止收益、opening=0、金额舍入、恒等式 property-style 参数测试。

## 验收

```powershell
python -m pytest tests/test_analytics_reconciliation.py -q --basetemp .pytest_tmp_ds011 -p no:cacheprovider
```

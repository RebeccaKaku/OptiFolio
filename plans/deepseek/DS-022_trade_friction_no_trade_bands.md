# DS-022：交易摩擦与不交易区间

**用户价值**：避免为了很小的仓位偏差付出申赎费、换汇费、锁定期和操作成本。  
**依赖**：DS-021。

## 允许修改

- 新增 `src/analytics/trade_friction.py`
- `src/analytics/new_money.py`（仅集成）
- 新增 `tests/test_trade_friction.py`
- `tests/test_new_money.py`

可只读复用 `src/core/fees.py`、`src/core/friction_data.py`；除非发现契约 bug，不修改它们。禁止数据库和交易执行。

## 契约

输入 proposal、买入/赎回费、管理费差、固定费用、FX spread/手续费、最小交易额、锁定期、预期持有期和 no-trade band。费用缺失必须标 unknown，不能默认 0。

输出分开不同单位：`gap_improvement_weight,total_known_cost_amount,unknown_costs,monetized_benefit?,net_monetized_benefit?,break_even_horizon?,no_trade,reasons,eligible_allocations`。所有成本换算到明确报告币种并带 FX 证据。只有调用方显式提供可审计的 monetized benefit/hurdle 时才计算净经济改善和 break-even。

## no-trade 规则

以下任一成立可建议不交易：偏离在带宽内；交易额低于最小额；显式 monetized benefit 不高于成本；锁定期不符合用途；关键成本未知导致无法判断。若没有 monetized benefit，`no_trade_due_to_economics=unknown`，不得把权重改善和金额成本硬比。`no_trade` 是计算结果，不是交易指令。

管理费是持有期流量，申赎/FX 是一次性成本，不能直接相加而不注明期限。不得把预期收益当确定收益；v1 可用目标缺口改善作为 benefit proxy，并明确方法。

## 必须测试与验收

零费用、固定+比例费、FX 双重成本、边界等于 band、最小额、成本>改善、未知费用、持有期、预算守恒集成。

```powershell
python -m pytest tests/test_trade_friction.py tests/test_new_money.py -q --basetemp .pytest_tmp_ds022 -p no:cacheprovider
```

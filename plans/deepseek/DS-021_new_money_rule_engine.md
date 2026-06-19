# DS-021：新钱投入规则引擎

**用户价值**：当有一笔新资金时，给出几套满足约束、可解释的投入方案，而不是一句模糊建议。  
**依赖**：DS-018、DS-020。

## 允许修改

- 新增 `src/analytics/new_money.py`
- 新增 `tests/test_new_money.py`

禁止数据库、自动下单、宏观预测、卖出现有持仓和声称全局最优。

## 输入

`new_cash_amount/currency`、canonical reporting currency、带 dated/source FX evidence 的换算表、current_total_value、当前 product/issuer/currency exposures、DS-020 gaps、候选产品、用途 bucket、币种用途约束、流动性下限、单产品/发行人上限、最小/最大交易额、允许保留现金比例。缺汇率时只允许同币种方案或标不可行。所有预算与投后权重在 reporting currency 中验证，同时保留原币金额。

## 输出

至少尝试三种 deterministic strategy：`gap_first`、`liquidity_first`、`diversification_first`。每个 proposal 返回 allocations、residual_cash、post_trade_weights、satisfied_constraints、binding_constraints、rejected_candidates、explanation、status。三策略只要求在专门构造的有权衡 fixture 中产生差异；无权衡输入允许结果相同。

硬约束必须全部满足；软偏好可权衡但要解释。预算恒等：`sum(allocations)+residual_cash=new_cash`。没有可行产品时允许 100% residual，不得强投。unknown 条款的产品不能被当作满足流动性或风险约束。

## 必须测试

单缺口、多缺口、币种用途、产品上限、发行人上限、最小额、金额不足、无可行产品、三策略差异、预算守恒、输入顺序不影响结果、Decimal 舍入 residual。

## 验收

```powershell
python -m pytest tests/test_new_money.py -q --basetemp .pytest_tmp_ds021 -p no:cacheprovider
```

# DS-018：流动性与永久损失风险

**用户价值**：把“短期净值波动”“暂时取不出来”“产品可能永久亏损”“条款未知”分开，避免所有风险混成一个红灯。  
**依赖**：DS-016、DS-017。

## 允许修改

- `src/analytics/liquidity.py`
- 新增 `src/analytics/permanent_loss.py`
- `src/analytics/rule_engine.py`（仅修单位错误与接入新报告）
- `tests/test_analytics_liquidity.py`
- `tests/test_analytics_rule_engine.py`
- 新增 `tests/test_permanent_loss.py`

禁止数据库、API/UI、预测违约概率和自动卖出建议。

## 必须先修复的现存风险

1. unknown 产品不得默认“7 天内”；未知存款不得默认 T+0。应进入 unknown bucket 并携带 warning。
2. `RuleEngine.run_from_reports` 不得把已经是 0～1 的 `ConcentrationItem.pct` 再除以 100；增加回归测试。

## 风险报告契约

逐持仓输出四个彼此独立的维度：

- `market_volatility`：正常价格波动；
- `liquidity_restriction`：锁定期、开放日、到账时间、赎回上限；
- `permanent_loss`：发行人信用、结构性条款、本金非保障、底层信用/久期风险；
- `data_unknown`：缺条款、缺穿透、陈旧数据。

每维度输出 `level=low|medium|high|unknown`、evidence、as_of、rule_id。unknown 不能折算成 low，也不能仅因波动高就判“永久损失高”。现金/存款也只有在产品条款和机构范围明确时才能判断流动性。

组合汇总同时提供金额和占比；分母仅使用已知组合市值并单列 unknown_value，不能让未知消失。

## 必须测试

活期、定期未到期、开放式基金、封闭理财、未知产品、正常美债久期波动、信用风险、结构性非保本、缺条款、集中度单位回归、warning 进入最终报告。

## 验收

```powershell
python -m pytest tests/test_analytics_liquidity.py tests/test_permanent_loss.py tests/test_analytics_rule_engine.py -q --basetemp .pytest_tmp_ds018 -p no:cacheprovider
```


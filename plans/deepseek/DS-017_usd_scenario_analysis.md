# DS-017：美元二维情景分析

**用户价值**：看到“美元产品本身收益 × USD/CNY 变化”组合后，对人民币财富的可能后果；这是压力测试，不是汇率预测。  
**依赖**：DS-013、DS-016。

## 允许修改

- 新增 `src/analytics/scenarios.py`
- 新增 `tests/test_scenarios.py`

禁止 API/UI、概率预测、数据库、宏观数据抓取和交易建议。

## 纯函数契约

输入：当前 USD 暴露本金（USD 或带现行汇率的 CNY）、产品本币回报情景数组、USD/CNY 变动情景数组、可选费用、人民币替代基准。输出二维矩阵，每格包含：`ending_value_usd,ending_value_cny,cny_return,local_component,fx_component,interaction,fees,relative_to_cny_benchmark`。

口径与 DS-014 完全一致：产品情景是扣费前 gross return；费用是在期末从 USD 金额扣除的独立 USD 金额，再按情景期末 FX 折 CNY。公式：`ending_usd = opening_usd*(1+r_product)-fee_usd`，`ending_cny = ending_usd*fx0*(1+r_usdcny)`。输入若已是净收益则必须显式 `fees_already_in_return=true` 且不再扣费。基准格（0% 产品、0% FX、0费用）的期末 CNY 金额必须等于当前值。

## 暴露规则

每项暴露带 `exposure_role=payoff_currency|lookthrough_economic|hedged`。人民币财富换算只按 payoff currency 施加 FX；look-through currency 只作为风险说明，除非调用方提供一个明确模型把该冲击映射为产品本币回报，否则不直接二次施压；hedged 暴露按已知对冲比例处理。unknown residual 单列且不受确定情景冲击。输入情景使用小数（-0.1 表示 -10%），越界和单位混用拒绝。

## 输出说明

每个结果都标 `scenario_not_forecast=true`；不得包含“买/卖/持有”文本或默认概率。默认网格可由 UI 未来提供，本模块不硬编码市场判断。

## 必须测试与验收

0/0 基准、产品正收益+美元贬值、双正/双负、交互项、费用、相对基准、直接/穿透去重、unknown 暴露、输入顺序稳定、Decimal 恒等。

```powershell
python -m pytest tests/test_scenarios.py -q --basetemp .pytest_tmp_ds017 -p no:cacheprovider
```

# DS-014：产品收益与汇率归因

**用户价值**：解释“美元计价赚了，但折成人民币反而不如人民币低收益产品”。  
**依赖**：DS-011、DS-013。

## 允许修改

- 新增 `src/analytics/return_attribution.py`
- 新增 `tests/test_return_attribution.py`

禁止 API/UI、预测、数据库和自动抓取。

## 契约与恒等式

对无期间外部现金流的单期持有，使用：

`R_CNY = (1 + R_local) * (1 + R_fx) - 1`

并报告 `local_return + fx_return + interaction = reporting_return`，其中 interaction=`R_local*R_fx`。有现金流时只接受上游提供且标记方法的回报或输出 `not_attributable`，不得自行套简单收益率。

固定 gross/net 口径：`R_local` 是扣费前产品回报；费用作为期末从产品计价币种扣除的独立金额，再按期末 FX 折算。若输入期末估值已净含费用，调用方必须标 `fees_already_in_closing_value=true`，bridge 只做展示而不得再次扣除。费用发生时点未知则金额归因降级。

金额 bridge：`closing_reporting = opening_reporting + gross_local_pnl_reporting + fx_effect + interaction_effect - fees_reporting + external_flows_reporting + unclassified`。产品本币损益、纯汇率影响、交互项、费用税费、外部现金流、未解释差额和相对人民币基准差均带币种、日期、质量和方法。

## 降级规则

期初为零、缺 FX、partial coverage、估值 stale、现金流时点未知时，不输出假精确百分比；返回 estimated/not_attributable 与原因。相对基准必须由调用方传入，不能默认银行利率。

## 固定案例

构造非真实金额：USD 产品两年本币 +8%，USD/CNY 变化 -10%，验证人民币回报为 -2.8%；再与 CNY +3% 基准比较，算术主动回报为 -5.8 个百分点。若输出相对财富比，则单独标为 `0.972/1.03-1≈-5.631%`，不得把两者混叫 relative return。明确这是数学 fixture，不是用户真实数据。

## 必须测试与验收

测试正/负产品收益、美元升贬、交互项、费用、基准、缺数据、期初零、恒等式容差。

```powershell
python -m pytest tests/test_return_attribution.py -q --basetemp .pytest_tmp_ds014 -p no:cacheprovider
```

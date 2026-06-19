# DS-013：原币/人民币双口径汇总

**用户价值**：既看美元产品本身表现，也看折成人民币后的财富结果。  
**依赖**：DS-012。

## 允许修改

- 新增 `src/analytics/currency_aggregation.py`
- 新增 `tests/test_currency_aggregation.py`

禁止抓取汇率、数据库、API、UI。

## 输入/输出

输入一组带 `amount,currency,quality` 的估值结果、报告币种（默认 CNY）和显式 `FxQuote(base,quote,rate,as_of,source,quality)`。输出：

- `by_original_currency`：每币种已知合计、未知条数；
- `reporting_total`：仅当所有纳入项有可用汇率时给精确 total，否则给 known_total + unknown_components；
- 每项 conversion evidence；
- 质量分桶：reported/estimated/stale/unknown。

## 金融规则

固定报价含义：1 base = rate quote。允许显式反向换算；禁止隐式三角换汇，除非调用方提供完整路径且输出路径。CNY→CNY rate=1 是单位恒等，不是市场汇率。小币种也计入，不因金额小而删除。负债/负金额必须保留符号。

使用 Decimal 并在最终展示层才舍入。汇率日期晚于估值日拒绝；陈旧阈值由参数传入。缺汇率时不能把该项当 0。

## 必须测试

CNY+USD+HKD、反向报价、负金额、缺汇率、stale、零金额、小币种、汇率方向反例、逐项折算和总额恒等式。

## 验收

```powershell
python -m pytest tests/test_currency_aggregation.py -q --basetemp .pytest_tmp_ds013 -p no:cacheprovider
```


# DS-023：标准产品比较器

**用户价值**：在同一用途下比较货币基金、美债类理财、存款等标准产品的到手收益、流动性和风险，而不是只看宣传收益率。  
**依赖**：DS-012、DS-016、DS-018、DS-022。

## 允许修改

- 新增 `src/analytics/product_comparison.py`
- `src/analytics/screening.py`
- 新增 `tests/test_product_comparison.py`
- `tests/test_analytics_screening.py`

禁止抓取产品、数据库、UI、推荐具体在售产品和跨用途总榜。

## 必须修复的现存风险

`ProductScreener` 当前不得再用 0 代替缺失指标。此任务明确升级其结果契约：metrics 允许 `None`，新增 coverage/incomparable/incomparable_reasons。use case 声明的关键字段任一缺失则 incomparable 且不参与总排名；非关键字段只在已知维度上按原权重重新归一化，并输出 `coverage=sum(known_original_weights)`。coverage 低于调用方阈值（默认 0.8）时同样不排名。不得用惩罚分或 0 猜测缺失值，并更新调用方/旧测试。排名同分时按 product_id 稳定打破，不依赖输入顺序。

## 比较输入

必须先指定 use case：币种、金额、预计持有期、流动性需求、风险容忍、是否允许 FX。每个产品字段：可比收益口径及期间、申赎/管理/FX费用、到账/锁定、久期、信用/本金结构、币种暴露、最低金额、数据 as_of/source/quality。

## 输出

逐产品返回 `net_yield_scenarios`（不是单点承诺）、known fees、liquidity、duration、credit/structure、FX、data_quality、coverage、incomparable_reasons。可提供透明的维度评分，但每个权重和贡献可追溯；任何关键字段未知时不得给无条件第一名。

收益必须统一期限、年化/累计、税前/税后口径；不能把七日年化、到期收益率、历史回报直接横比。不同币种必须显示 FX 情景而非假设不变。

## 必须测试

同用途三产品、期限换算、费用后排名变化、流动性硬约束、缺失收益/费用/信用、不同币种、七日年化误用反例、screening missing 回归、输入顺序稳定。

## 验收

```powershell
python -m pytest tests/test_product_comparison.py tests/test_analytics_screening.py -q --basetemp .pytest_tmp_ds023 -p no:cacheprovider
```

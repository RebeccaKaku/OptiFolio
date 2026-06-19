# DS-020：目标区间与仓位缺口

**用户价值**：知道哪些配置偏低、合理或偏高，而不是假装存在唯一“最优权重”。  
**依赖**：DS-013、DS-016、DS-019。

## 允许修改

- 新增 `src/analytics/allocation_targets.py`
- 新增 `tests/test_allocation_targets.py`

如确需持久化目标，必须拆成后续独立任务并使用届时 next available schema version；不得在本任务顺手改数据库。禁止 optimizer、Black-Litterman、交易建议和 UI。

## 纯函数契约

`TargetRange(dimension,bucket,min_weight,max_weight,priority?)`；`TargetSet(scope,denominator_value,reporting_currency,exhaustive,mutually_exclusive,ranges)`。dimension 可为 `purpose_bucket|currency|asset_class|issuer|product`。输入当前已知暴露、unknown 暴露和 TargetSet；输出每项：`current_weight,min,max,status=below|within|above|unknown,gap_to_min,gap_to_max,amount_range,quality,reasons`。amount_range 以 denominator_value 计算。

## 校验与金融语义

- 每项 `0<=min<=max<=1`；互斥且穷尽维度的 min 总和不得>1、max 总和不得<1；非穷尽维度不做错误的加总约束。
- 分母和 scope 必须明确；个人总资产、某资金桶、某币种不可混用。
- unknown exposure 足以改变分类时返回 unknown/ambiguous，不能强判超配或低配。
- 只报告区间和缺口，不输出最优点、不假设交易可行。

## 必须测试

below/within/above、边界相等、不可行区间、不同 scope、unknown 改变判定、金额与权重一致、空组合、负债/负值拒绝、稳定排序。

## 验收

```powershell
python -m pytest tests/test_allocation_targets.py -q --basetemp .pytest_tmp_ds020 -p no:cacheprovider
```

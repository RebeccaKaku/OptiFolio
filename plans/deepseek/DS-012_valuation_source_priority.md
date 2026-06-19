# DS-012：估值来源优先级与证据

**用户价值**：每个资产数字都能回答“哪一天、从哪里来、是否估算”。  
**依赖**：DS-008；可读取 FinData 已有 serving 接口，不修改 FinData。

## 允许修改

- 新增 `src/core/book_valuation.py`
- 新增 `src/services/book_valuation_service.py`
- 新增 `tests/test_book_valuation.py`

禁止 API/UI、数据库迁移、网络抓取和写入市场数据库。

## 估值候选与优先级

输入 position 与若干 `ValuationCandidate(amount?,price?,quantity?,currency,effective_date,known_at,source_id,source_type,quality)`。`known_at` 用于禁止未来信息；price candidate 必须同时携带可相乘的 quantity。候选类型按规则选择：

1. 同一 as_of 的人工确认 market_value；
2. 不晚于 as_of 的公开 NAV/price × quantity；
3. 较早人工报告值的 stale carry-forward；
4. 无候选则 unknown。

优先级不是盲目覆盖：未来数据永不允许；公开值超过按产品类型配置的新鲜度阈值后只能 stale；人工值日期不匹配不能标 reported-current。输出字段明确为：`amount,currency,valuation_date,known_at,source_type,source_id,quality, freshness,is_estimate,age_days,warnings`。其中 quality=`confirmed|reported|estimated|unknown`，freshness=`current|stale|unknown`，二者不得混成一个枚举。

`BookValuationService` 通过构造函数注入只读 observation provider；测试使用 fake provider。不得直接实例化或修改 FinData，不得使用任何硬编码 FX fallback。

## 规则

- quantity 缺失时不得用公开价格推市值；
- market_value=0 是已知零，None 是未知；
- 不得假设 price currency 等于 position currency；币种不符返回 unknown/warning；
- 不得用 cost basis 作为当前市值；
- carry-forward 必须保留原估值日，不得改成今天。

## 必须测试

四级优先级、未来值拒绝、stale 阈值、quantity 缺失、币种错配、零值、同优先级 deterministic tie-break、来源证据完整、无候选 unknown。

## 验收

```powershell
python -m pytest tests/test_book_valuation.py -q --basetemp .pytest_tmp_ds012 -p no:cacheprovider
```

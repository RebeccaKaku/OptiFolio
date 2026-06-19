# DS-016：产品暴露快照仓储

**用户价值**：银行理财和公募基金不能只按产品名称统计；系统要知道其底层美债、A股、美股、黄金、币种、久期和信用暴露，同时诚实保留未知部分。  
**依赖**：DS-015；当前预期 schema v8。

## 允许修改

- `src/core/portfolio_book_db.py`
- 新增 `src/domain/exposures.py`
- `src/services/portfolio_book_service.py`
- 新增 `tests/test_exposure_snapshots.py`
- `tests/test_portfolio_book_db.py`

禁止修改现有 `src/analytics/exposure.py` 的 Level-0 接口、API/UI、抓取器和自动推断模型。

## schema v9

新增 `exposure_batches`：`exposure_batch_id,product_id,as_of,known_at,source,quality,status,notes`。status=`draft|confirmed|superseded`。

新增 `product_exposures`：`exposure_batch_id,dimension,bucket,weight_ppm,method,source_ref,notes`。dimension 至少允许 `asset_class|currency|region|duration|credit_quality|commodity`；method=`actual|reported|estimated|proxy|unknown`；weight 使用整数 ppm（0～1,000,000），领域层转换 Decimal，禁止 REAL。

同一产品、批次、dimension、bucket 唯一。每个 dimension 已知 weight 总和不得超过 1；小于 1 时查询结果必须生成 `unknown_residual=1-sum(known)`，绝不归一化为 100%。unknown residual 不是一条伪造暴露。

## 状态与时间语义

只有 confirmed 批次可供风险分析。draft 可修改；confirmed 不可修改；更正使用新批次并 supersede 旧批次。`as_of` 是暴露所对应日期，`known_at` 是用户/系统当时获知日期，防止未来信息泄漏。选择历史暴露时要求 known_at 不晚于分析时点。

quality=`reported|estimated|stale|unknown`；产品营销名称不得自动推出“低风险”或 100% 美债。proxy 必须保存代理依据。

## 必须测试

v8→v9 与新库初始化、超 100% 拒绝、低于 100% 保留 residual、不同 dimension 独立计和、draft/confirmed/superseded、历史 point-in-time known_at、防未来信息、method/quality 校验、Decimal 边界。

DDL 明确 PK/FK/CHECK/UNIQUE/索引，exposure 行随 batch 级联删除；migration 单事务且失败回滚。同步更新 version-aware backup required tables；测试 v9 backup/restore 往返，并验证删除 exposure_batches 或 product_exposures 后备份验证失败。

## 验收

```powershell
python -m pytest tests/test_exposure_snapshots.py tests/test_portfolio_book_db.py -q --basetemp .pytest_tmp_ds016 -p no:cacheprovider
```

非目标：自动穿透基金、解析季报、风险评分、页面展示。

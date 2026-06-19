# DS-019：核心、用途储备与学习资金桶

**用户价值**：同样是美元资产，出国会议储备与练习市场判断的钱应使用不同基准和风险规则。  
**依赖**：DS-015、DS-018；当前预期 schema v9。

## 允许修改

- `src/core/portfolio_book_db.py`
- 新增 `src/domain/purpose_buckets.py`
- `src/services/portfolio_book_service.py`
- `src/api/portfolio_book_api.py`
- 新增 `tests/test_purpose_buckets.py`
- `tests/test_portfolio_book_db.py`

禁止把 bucket 写进 ProductDefinition、优化算法、自动分类和家庭资产估值。

## schema v10

`purpose_buckets(bucket_id,name,bucket_type,base_currency,benchmark_id?,liquidity_horizon_days?,risk_notes,status,created_at,updated_at)`；bucket_type 最少 `core|purpose_reserve|learning`。

`position_bucket_allocations(allocation_id,batch_id,account_id,product_id,bucket_id,allocation_ppm,notes)`。allocation 使用整数 ppm（0～1,000,000），禁止 REAL；同一 confirmed position 分配总和不得超过 1,000,000；不足部分显式 unassigned。UNIQUE(batch_id,account_id,product_id,bucket_id)，且 allocation 必须引用真实 confirmed position。同一产品可跨 bucket，同一份资产不能重复计入。

## 历史与范围

allocation 绑定 confirmed snapshot batch；目的改变写到新批次，不回写历史。bucket 加总必须还原已分配的个人账本资产。家庭只持人民币但金额未知，可作为 bucket 风险备注，不可加入分母、目标或可投资现金。

## API

提供 bucket create/list/update/deactivate、为指定 confirmed position 设置 allocation、查询 ratio/unassigned 汇总。删除改为 deactivate；有历史 allocation 的 bucket 不物理删除。金额、币种估值和风险摘要需要组合 DS-012/015/018，留给后续 read-model 集成，不得塞进 repository 或本任务的 portfolio book service。

## 必须测试

v9→v10、新库、跨 bucket、总和>1拒绝、未分配 residual、同产品不同目的、历史不变、inactive bucket 新分配拒绝、金额加总不重复、家庭未知不进数值。

DDL 明确 PK/FK/CHECK/UNIQUE/索引和删除策略；migration 单事务且失败回滚。同步更新 version-aware backup required tables；测试 v10 backup/restore 往返，并验证删除任一 bucket/allocation 新表后备份验证失败。

## 验收

```powershell
python -m pytest tests/test_purpose_buckets.py tests/test_portfolio_book_db.py -q --basetemp .pytest_tmp_ds019 -p no:cacheprovider
```

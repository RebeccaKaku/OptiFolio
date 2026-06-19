# DS-008：快照草稿、进度与确认 API

**用户价值**：首次建账可以分几天完成，用户始终知道哪些账户已录、部分录或确认为空。  
**依赖**：DS-007。

## 允许修改

- `src/services/portfolio_book_service.py`
- `src/api/portfolio_book_api.py`
- `tests/test_portfolio_book_service.py`
- `tests/test_portfolio_book_api.py`

- `src/core/portfolio_book_db.py`（快照状态原子门控与最小读取；禁止迁移）
- `tests/test_portfolio_book_db.py`

禁止 UI、schema 变更和分析逻辑。

## API 契约

- `POST /api/book/snapshot-batches`：创建 draft；字段 `batch_id,as_of,source,quality,notes`。
- `GET /api/book/snapshot-batches/{id}`：批次、positions、account_coverage、progress。
- `PUT /api/book/snapshot-batches/{id}/accounts/{account_id}/coverage`。
- `POST /api/book/snapshot-batches/{id}/positions`。
- `POST /api/book/snapshot-batches/{id}/validate`：只校验，不改变状态。
- `POST /api/book/snapshot-batches/{id}/confirm`：原子确认。

position 字段：`account_id,product_id,quantity?,market_value?,cost_basis?,currency,source?,quality?,notes?`。quantity 与 market_value 至少一个存在；未知不得传 0。coverage 仅 `complete|partial|empty`。

validate 返回：`is_confirmable,is_complete,errors[],warnings[],account_progress[]`。`partial` 可确认但必须 warning；零账户不可确认；`empty` 不可含 position。confirmed/superseded 批次不可修改。

## 并发与幂等语义

- 相同 batch_id 重复创建返回 409；
- 第一次确认成功；再次确认返回 409，响应明确 `already_confirmed`，不伪装成功；
- 确认与新增 position/coverage 竞争时由数据库事务保证只出现“写入后确认”或“确认后拒绝”。不得采用先 SELECT 后在另一事务写入的 TOCTOU；使用 `BEGIN IMMEDIATE` 或条件写入+rowcount，并增加两个独立连接的竞争测试；
- validate 不锁定、不确认、不写数据。

## 金融语义

draft 永远不进入首页和收益计算。`complete` 表示该账户截至 as_of 已完整覆盖；`empty` 表示主动确认无余额；缺少 coverage 表示未录，不等于空。

## 必须测试

完整建账、partial 警告、empty、未知账户/产品、负数、quantity-only、market-value-only、重复确认、确认后写入拒绝、validate 无副作用、draft 不被“最近确认批次”查询选中（若该查询存在）。

## 验收

```powershell
python -m pytest tests/test_portfolio_book_service.py tests/test_portfolio_book_api.py tests/test_portfolio_book_db.py -q --basetemp .pytest_tmp_ds008 -p no:cacheprovider
```

非目标：删除/编辑 position、批量导入、OCR、现金流 UI、收益计算。

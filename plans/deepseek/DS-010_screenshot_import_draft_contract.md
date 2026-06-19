# DS-010：截图导入草稿的数据契约

**用户价值**：未来可由截图减少手工输入，但任何识别错误都不能污染正式账本。  
**依赖**：DS-008。当前任务不接 OCR 模型。

## 允许修改

- `src/core/portfolio_book_db.py`
- 新增 `src/domain/import_drafts.py`
- 新增 `src/services/import_draft_service.py`
- `tests/test_portfolio_book_db.py`
- 新增 `tests/test_import_draft_service.py`

禁止 API/UI、OCR、图像处理、外部调用、把图片二进制写入 SQLite、自动创建账户/产品/快照。

## schema v8

新增：

- `import_drafts(import_id,contract_version,target_kind,source_type,source_ref,status,created_at,updated_at)`；target_kind=`account|product|position`，status=`pending|reviewed|applied|rejected`。
- `import_candidates(candidate_id, import_id, field_name, raw_text, proposed_value_json, confidence, review_status, corrected_value_json, notes)`；review_status=`unreviewed|accepted|corrected|rejected`。

`source_ref` 只能是受控的相对引用或不可逆 hash，不得保存系统临时绝对路径、用户名、账号全号或原图内容。confidence 为 `[0,1]` 或 null；null 表示提取器未提供。

所有 text/JSON 字段（raw_text、proposed、corrected、notes、source_ref）写入前统一敏感检测与脱敏；账号提示只允许掩码后四位。命中银行卡号、客户号、证件号、密码或 token 的原始文本不得落库，不能只检查 source_ref。

## 领域与 service 契约

提供创建 import draft、添加候选、逐字段审核、拒绝草稿、生成“待应用 payload”方法。contract v1 必填规则：account=`name,base_currency`；product=`name,product_type,currency`；position=`account_id,product_id,currency` 且 `quantity|market_value` 至少一项。只有对应 target_kind 的必填/条件字段均 accepted/corrected 且用户显式 `mark_reviewed` 后才生成版本化 payload preview；本任务不得调用正式账本写入。

候选字段至少可表达：institution/account_hint/product_name/product_type/currency/as_of/quantity/market_value。字段值保留 `raw_text` 与结构化 proposed/corrected 两层。低于可配置阈值（默认 0.8）的字段必须出现在 `needs_attention`，但高置信也不能自动 accepted。

## 安全与金融语义

- OCR 候选永远不是事实；confidence 不是金融数据质量。
- `¥/$` 不能在无上下文时自动映射币种；日期缺年、金额含“万”、净值与市值混淆均须人工修正。
- applied 状态在后续任务实现；本任务只能产生 payload preview。

## 必须测试

v7→v8 无损迁移及回滚；新库 v8；候选 JSON 往返；低置信提示；高置信不自动接受；逐字段 correction；未审完不能 reviewed；reviewed 后只生成 preview；绝对路径和敏感字段拒绝；状态转换非法时拒绝。

DDL 必须写明 PK、FK（candidate→draft，ON DELETE CASCADE）、NOT NULL、CHECK、UNIQUE 和按 import/status 的索引；migration 单事务，失败时 schema version 与旧表不变。同步更新 version-aware backup required tables：v8 备份必须包含两张 import 表；测试 backup/restore 往返，并验证删除任一新增表后 `verify_backup()` 返回 false。

## 验收

```powershell
python -m pytest tests/test_portfolio_book_db.py tests/test_import_draft_service.py -q --basetemp .pytest_tmp_ds010 -p no:cacheprovider
```

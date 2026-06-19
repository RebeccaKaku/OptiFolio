# DS-024：投资决策日志

**用户价值**：训练“对资本市场的判断能力”，把当时知道什么、为什么持有、什么会证明自己错记录下来，便于真正复盘。  
**依赖**：DS-019，并按路线图在 DS-023 后执行；当前 schema v10。

## 允许修改

- `src/core/portfolio_book_db.py`
- 新增 `src/domain/decision_journal.py`
- 新增 `src/services/decision_journal_service.py`
- `src/api/portfolio_book_api.py`
- 新增 `tests/test_decision_journal.py`
- `tests/test_portfolio_book_db.py`

禁止 AI 自动写结论、改历史记录、下单、保存真实截图或秘密。

## schema v11

`decisions(decision_id,title,decision_type,as_of,status,account_id?,product_id?,snapshot_batch_id?,created_at)`。

`decision_revisions(revision_id,decision_id,revision_no,thesis,baseline,priced_in,evidence_json,scenarios_json,position_reason,invalidation_conditions,review_at,author_type,created_at)`。

revision 追加写，禁止 UPDATE 正文；更正创建新 revision。status=`open|review_due|closed|invalidated`。evidence 只存引用、日期、摘要和来源类型，不复制大段版权内容。

DDL 必须含 FK、NOT NULL、CHECK、索引与 UNIQUE(decision_id,revision_no)。repository 不提供 revision UPDATE/DELETE；并发 append 在一个写事务内计算下一 revision_no，冲突重试或明确返回 409，不得丢失一条 revision。

## API/行为

create decision、append revision、list/filter、get timeline、mark status、list reviews due。创建时强制 thesis、baseline、至少一个 invalidation condition 和 review_at；“因为会涨”不足以作为结构化理由但可作为文本由用户决定，service 只校验字段存在。

历史复盘必须能关联当时 snapshot 和未来可选 model version；不存在引用时返回 422。AI author_type 的 revision 必须显式标记，且不能覆盖 human revision。

## 必须测试与验收

v10→v11、新库、创建/追加、revision 连续、历史不可变、到期查询、状态转换、引用校验、AI/人工区分、敏感字段拒绝。

Migration 单事务且失败回滚；同步更新 version-aware backup required tables；测试 v11 backup/restore 往返，并验证删除 decisions 或 decision_revisions 后备份验证失败。

```powershell
python -m pytest tests/test_decision_journal.py tests/test_portfolio_book_db.py -q --basetemp .pytest_tmp_ds024 -p no:cacheprovider
```

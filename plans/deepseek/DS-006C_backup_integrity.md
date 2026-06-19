# DS-006C：备份完整性与原子恢复

本任务在 DS-006B 合并后执行，是开放 Personal Book API 前的最后一道地基验收。

## 用户价值

首次建账可能花很久。备份按钮必须真正保护账本，而不是复制出一个“能打开版本号但内部已损坏”的文件。

## 依赖

- DS-006A、DS-006B 已合并；
- 不新增 schema version，除非确有结构变化并在汇报中说明。

## 允许修改

- `src/core/portfolio_book_db.py`
- `tests/test_portfolio_book_db.py`

## 禁止修改

- API、service、UI、FinData、local、资产注册表和其他业务模块。

## backup() 要求

- 源数据库必须存在且已初始化；不存在时拒绝，不能因 connect 创建空源；
- target 与 source 解析后相同则拒绝；
- target 已存在时默认拒绝，除非新增显式 overwrite 参数；
- 使用 SQLite backup API；
- 完成后立即执行完整验证；
- 验证失败时删除本次生成的不完整 target；
- 不在日志中打印个人数据。

## verify_backup() 要求

至少验证：

- 是可打开的 SQLite 数据库；
- `PRAGMA integrity_check` 返回 `ok`；
- schema metadata 存在且版本合法；
- 必要核心表与当前 schema version 一致；
- 更高版本应被识别为“不兼容”，不能简单返回可恢复。

可以保留布尔接口，也可以增加一个内部详细结果对象；不要扩张成通用备份框架。

## restore_from() 要求

- 恢复前完整验证备份；
- 不兼容高版本拒绝；
- 低版本备份恢复后运行正常 migration 到当前版本；
- 使用目标同目录的临时文件完成恢复、验证和 migration，再通过原子替换更新目标；
- 任何失败都保留原目标数据库；
- 临时恢复文件在成功或失败后都清理；
- overwrite=False 时目标存在继续拒绝。

## 必须新增的测试

- 不存在源不能备份且不会创建源；
- source==target 被拒绝；
- 已存在 target 默认拒绝；
- integrity_check 失败的数据库不能通过验证；
- 只伪造版本表但缺核心表不能通过；
- 低版本备份恢复后升级到当前版本且数据保留；
- 高版本备份拒绝；
- 模拟恢复中途失败，原目标仍可读取且数据不变；
- 成功恢复后无临时文件残留。

## 验证

```powershell
python -m pytest tests/test_portfolio_book_db.py -q --basetemp .pytest_tmp_ds006c -p no:cacheprovider
```

不得创建或提交 `local/portfolio_book.sqlite`、测试数据库或备份文件。

## 最终汇报

说明原子替换策略、失败保护、兼容版本行为、测试结果及Windows路径注意事项。

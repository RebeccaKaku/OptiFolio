# DS-027：研究模型晋升注册表

**用户价值**：研究代码可以大胆试验，但只有被验证、人工批准且可撤回的版本才能成为正式计算器的可选输入。  
**依赖**：DS-021、DS-022、DS-024、DS-026。

## 允许修改

- 新增 `src/domain/model_governance.py`
- 新增 `src/research/model_registry.py`
- 新增 `tests/test_model_registry.py`
- 可新增 `config/research_models.yaml`，但只能包含 `schema_version` 和空 models 列表

禁止修改 backtest/qlib 实现、注册虚假 production 模型、自动审批、自动交易和数据库 migration。

## 注册项

字段至少：`model_id,version,status,code_ref,input_contract,output_contract,data_cutoff,training_window,validation_window,validation_metrics,leakage_checks,stability_checks,known_limitations,approved_use_cases,forbidden_use_cases,expires_at,created_at`。

状态：`experimental|validated|approved|retired`。registry 是只读配置快照；状态转换是纯函数，返回新的内存 snapshot，绝不在运行时改 tracked YAML。approved 可随时 retired；retired 不可重新启用，必须新版本。validated 要求验证证据齐全；approved 还要求 `human_approver,approved_at,decision_journal_id`。decision journal 是否存在通过注入的只读 validator 验证，registry 不直接访问数据库。

## 消费边界

正式计算器只可查询 `approved`、未过期、use case 匹配、输入契约匹配的模型；默认 registry 为空即不使用模型。任何 experiment 输出都不能通过传入 model_id 绕过 registry。返回建议时必须携带 model/version/data_cutoff/limitations。

registry 加载失败、schema/内容校验错误、未知状态时 fail closed。本任务不设计数字签名。生产配置保持 schema_version+空 models；状态测试只使用临时 fixture/内存 snapshot。配置不得含 pickle 路径、任意 import 字符串、命令或 secret。

## 必须测试

空 registry、状态转换、缺验证证据、缺人工审批、过期、use case 不符、retire、版本并存、绕过尝试、恶意配置字段、fail closed、审计信息完整。

## 验收

```powershell
python -m pytest tests/test_model_registry.py -q --basetemp .pytest_tmp_ds027 -p no:cacheprovider
```

完成 DS-027 不代表模型已经可用；仓库默认仍应没有 approved 模型。

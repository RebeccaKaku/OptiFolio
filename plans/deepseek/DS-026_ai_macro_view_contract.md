# DS-026：AI 宏观观点契约

**用户价值**：让 AI 的宏观判断成为可质疑、会过期的情景材料，而不是一句权威口吻的交易指令。  
**依赖**：DS-024；可只读使用现有 macro observations。本任务不调用 LLM。

## 允许修改

- 新增 `src/domain/macro_view.py`
- 新增 `src/services/macro_view_validator.py`
- 新增 `tests/test_macro_view_validator.py`

禁止持久化 migration、模型/provider 调用、网络、修改 scheduler/observations、交易建议和自动写入计算器。

## 契约

`MacroView` 必须包含：`view_id,version,as_of,observation_cutoff,scope,horizon,claim,supporting_evidence[],opposing_evidence[],scenarios[],confidence,invalidation_conditions[],expires_at,author_model,created_at`。

Evidence：`series_or_source_ref,observed_at,known_at,summary,direction`。Scenario：`name,probability,assumptions,calculator_inputs`。概率总和在容差内等于 1；confidence `[0,1]` 且不能替代概率。

## 验证状态

validator 输出 `valid_for_experiment,valid_for_calculator_candidate,errors,warnings`。缺反对证据、缺日期、证据晚于 cutoff、已过期、概率不和为 1、无失效条件时拒绝。`calculator_inputs` 只能是白名单情景参数，禁止 `buy/sell/ticker/amount/order` 等交易指令字段。

任何有效观点默认也只进入 experiment；成为 calculator candidate 仍需 DS-027 人工晋升。validator 不评价观点真假，只评价结构、时间一致性和可审计性。

## 必须测试与验收

完整观点、概率边界、过期、未来证据、只有支持无反对、trade instruction 注入、未知字段、模型版本、确定性序列化。

```powershell
python -m pytest tests/test_macro_view_validator.py -q --basetemp .pytest_tmp_ds026 -p no:cacheprovider
```


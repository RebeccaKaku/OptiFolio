# DS-025：美元美债理财案例页

**用户价值**：用用户最关心的真实决策类型学习：为何美元产品本币赚钱，换回人民币后却可能落后于人民币低收益替代品。  
**依赖**：DS-014、DS-017、DS-023、DS-024。

## 允许修改

- 新增 `src/analytics/case_study.py`
- 新增 `src/services/case_study_service.py`
- 新增 `src/api/case_study_api.py`
- `src/services/application.py`
- `src/api/fastapi_app.py`（仅 include router）
- `src/api/static/` 下新增案例页面
- 新增 `tests/test_case_study.py`

禁止在代码、fixture、截图、文档写用户真实金额/银行/产品名；禁止联网和给出买卖指令。

## 输入与输出

v1 输入由用户或测试传入：期初/期末 USD 估值、费用、两端 USD/CNY、同期间 CNY 替代基准、数据质量、可选情景网格。默认要求期间无外部现金流。若存在现金流，调用方必须另传已计算回报及 `return_method=TWR|MWR|caller_supplied`、现金流时点和 DS-006B 分类；本模块只桥接，不自行猜收益。输出：

1. USD 产品收益；
2. FX 影响与交互项；
3. CNY 财富结果；
4. CNY 替代基准结果；
5. 费用/换汇摩擦；
6. 相对基准差与不可归因项；
7. 事实、假设、主观观点分别列示。

所有项目必须能由输入回算；不完整数据降级，不推断缺失换汇价。`CaseStudyService` 组织 DS-014/017/023 纯计算，路由只解析 HTTP 并调用 service。页面通过独立 router 挂载，提供金额隐藏模式和比例模式。本任务只能输出 `journal_draft` 供用户检查，不保存到 decision journal；持久化需用户在后续显式提交。

## 固定测试

只使用合成比例和小额虚构金额；覆盖产品赚/汇率亏、产品亏/汇率赚、费用、现金流、缺基准、缺 FX、情景不是预测、桥接恒等式、页面无真实敏感字符串。

## 验收

```powershell
python -m pytest tests/test_case_study.py -q --basetemp .pytest_tmp_ds025 -p no:cacheprovider
```

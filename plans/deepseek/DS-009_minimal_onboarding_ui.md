# DS-009：最小手工建账界面

**用户价值**：用户只用浏览器即可录入人民币存款和美元理财，并可中断后继续。  
**依赖**：DS-007、DS-008。

## 允许修改

- `src/api/static_dashboard.py`
- `src/api/fastapi_app.py`（仅挂载/入口）
- `src/api/static/` 下新增原生 HTML/CSS/JS
- `tests/test_fastapi_app.py`
- 新增 `tests/test_portfolio_book_ui.py`

禁止引入 React/Vue/Node 构建链，禁止修改 service/database，禁止真实数据和外部 CDN。

## 页面流程

入口 `/book`，四步向导：

1. 账户：查看、新建、停用；解释 personal/joint，不支持家庭未知资产。
2. 产品：新建存款/银行理财/公募基金；币种必填，未知条款可留空。
3. 快照：选择 as_of，逐账户标记 complete/partial/empty，录 quantity 或报告市值。
4. 检查确认：展示 errors/warnings/覆盖进度，用户显式确认。

刷新后从 API 恢复 draft，不依赖 localStorage 作为事实来源。网络请求失败时保留表单内容并提示重试；不得显示“保存成功”。金额输入保留用户文本，提交前校验；不使用 JS 浮点做合计。

## 可用性要求

- 所有输入有 label、错误信息和键盘可达按钮；
- 明确区分“0”“未知”“未录”；
- 美元产品显示“计价币种 USD”，不暗示账户或报告币种相同；
- 确认前显示不可逆提示；confirmed 后表单只读；
- 无外网可使用；不加载字体、分析脚本或 CDN。

## 验收场景

自动测试使用 pytest/TestClient 验证页面入口、静态资源、自包含依赖和 JS 中的 API/错误处理关键契约；本任务不新增 Playwright/npm 依赖。Codex 审查阶段再用应用内浏览器走通真实流程：创建人民币存款账户和产品；创建美元理财账户和产品；刷新后补齐快照；一个账户 complete、另一个 partial；看到 warning 后确认；刷新后仍为 confirmed。另测 API 500、重复 ID、非法金额和无账户批次。

## 验收命令

```powershell
python -m pytest tests/test_portfolio_book_ui.py tests/test_fastapi_app.py -q --basetemp .pytest_tmp_ds009 -p no:cacheprovider
```

最终汇报附页面入口、自动化场景和手工检查步骤。非目标：视觉大改、图表、OCR、收益首页、移动 App。

# DS-015：“我的钱”可信首页

**用户价值**：回答总共有多少钱、放在哪里、今天能否可靠判断赚亏，以及哪些数字未知。  
**依赖**：DS-009～DS-014；当前 schema v8。

## 允许修改

- 新增 `src/services/my_money_service.py`
- `src/services/portfolio_book_service.py`
- `src/core/portfolio_book_db.py`（仅补 latest/list/period 读取；禁止迁移）
- 新增 `src/api/my_money_api.py`
- `src/services/application.py`
- `src/api/fastapi_app.py`
- `src/api/static/` 下新增或修改 book 首页文件
- 新增 `tests/test_my_money_service.py`
- 新增 `tests/test_my_money_api.py`
- `tests/test_portfolio_book_ui.py`
- `tests/test_portfolio_book_service.py`
- `tests/test_portfolio_book_db.py`

禁止修改 legacy dashboard 的金融语义、数据库 schema、自动抓取和图表框架。

database/service 必须提供稳定的只读接口：按 as_of 选择最近 confirmed batch、列出相邻 confirmed batches、读取期间 cashflows。查询必须排除 draft/superseded；不得由 `MyMoneyService` 通过 `connect()` 自写 SQL。

## API

`GET /api/book/summary?as_of=YYYY-MM-DD&reporting_currency=CNY`

返回：最近可用 confirmed batch、覆盖状态、原币合计、报告币种 known total/unknown components、按账户/产品/币种分组、quality buckets、估值证据摘要、收益状态。

收益状态只能是：

- `available`：有相邻完整 confirmed 快照、现金流可解释、估值/FX 足够；
- `estimated`：允许估算但明确列原因；
- `unavailable`：无基期、partial、关键汇率/估值缺失等。

不得因为系统日期变了就显示“今日收益”。只有两端都是对应交易/估值日且满足完整条件时才可用 `today` 标签，否则使用“自上次完整快照以来”。

## 页面

`/book` 首屏显示：已知总资产、未知金额提示、最近快照日期、覆盖完整度、账户/币种/产品分布、确认/估算/陈旧/未知金额、收益可用性和原因。不得混入技术资产 registry 或市场全量列表。金额可隐藏；页面不向第三方发送数据。

## 必须测试

完整 CNY、CNY+USD、缺 FX、partial、stale、只有一个快照、外部入金、unknown 产品、报告币种切换、legacy dashboard 不回归。UI 断言 unavailable 时绝不出现数值“今日收益”。

## 验收

```powershell
python -m pytest tests/test_my_money_service.py tests/test_my_money_api.py tests/test_portfolio_book_ui.py tests/test_fastapi_app.py -q --basetemp .pytest_tmp_ds015 -p no:cacheprovider
```

完成后 M2 才算形成端到端闭环。

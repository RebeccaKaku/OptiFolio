# DS-007：账户与产品 Service/API

**状态**：2026-06-19 已实现并通过 Codex 审查；专项 222 项、全量 869 项测试通过，等待用户决定是否提交。  
**用户价值**：让本地界面能够安全管理“钱放在哪里”和“买了什么”，不再直接编辑 YAML 或数据库。  
**依赖**：DS-006A/B/C 已完成；当前账本 schema v7。

## 必须阅读

- `plans/deepseek/README.md`
- `src/core/portfolio_book_db.py`
- `src/domain/products.py`
- `src/services/application.py`
- `src/services/response.py`
- `src/api/fastapi_app.py`
- `tests/test_fastapi_app.py`

## 允许修改

- 新增 `src/services/portfolio_book_service.py`
- 新增 `src/api/portfolio_book_api.py`
- `src/core/portfolio_book_db.py`（仅补 list 查询和异常归一化；禁止迁移）
- `src/services/application.py`
- `src/api/fastapi_app.py`
- `tests/test_portfolio_book_db.py`
- 新增 `tests/test_portfolio_book_service.py`
- 新增 `tests/test_portfolio_book_api.py`

禁止修改数据库 schema、现有 portfolio v1/v2 API、静态页面、`FinData/` 和 `local/`。

## 输入/输出契约

API 前缀 `/api/book`。实现：

- `GET /accounts?status=active|inactive|all`
- `POST /accounts`
- `GET /accounts/{account_id}`
- `PATCH /accounts/{account_id}`
- `POST /accounts/{account_id}/deactivate`
- `GET /products`
- `POST /products`
- `GET /products/{product_id}`
- `PUT /products/{product_id}`

账户创建字段沿用 database；默认 `ownership_scope=personal`，但响应必须明确返回。产品字段映射 `ProductDefinition`，未知扩展字段只允许放在 `metadata`。不得接收密码、银行卡号、客户号、证件号等字段；检测到常见私密字段返回 422。

成功响应使用 `{success,data,message,error,timestamp}`；创建返回 201，查询成功 200，不存在 404，重复 ID 409，业务校验 422，非预期错误 500。不得把 SQLite 异常原文暴露给客户端。

## 实现要求

1. `PortfolioBookService` 注入 `PortfolioBookDatabase`，测试不得使用默认 `local/` 路径。
2. service 提供 list/get/create/update/deactivate；把 sqlite row 和 dataclass 转为纯 JSON dict。
3. API 使用独立 `APIRouter` 和 Pydantic 请求模型，模型设置 `extra='forbid'`；路由中不得写 SQL、构造数据库连接或复制金融校验。
4. `ApplicationServices` 懒加载账本 service；允许测试覆盖依赖或传入临时数据库。
5. product update 的 URL ID 必须与 body ID 一致；不一致返回 422。
6. 列表顺序稳定：账户按 name/account_id，产品按 name/product_id。
7. database 只新增 `list_accounts(status)` 与 `list_products()` 等最小读方法；service 不得通过 `connect()` 自写 SQL。
8. 若浏览器跨源调用，CORS 仅补上本任务实际使用的 PATCH/PUT；不开放任意新 method/header。

## 非目标

不做删除、分页、认证、截图、快照、现金流、UI、估值或旧 YAML 迁移。

## 必须测试

- service CRUD、停用、缺失 ID、重复 ID、非法币种/ownership；
- 产品 metadata 往返且未知条款保持未知；
- API 状态码和统一响应；
- 私密字段拒绝且响应不回显原值；
- PATCH/PUT CORS preflight 返回允许的方法；
- 路由通过 mock service 证明不直接访问数据库；
- 现有 FastAPI 测试无回归。

## 验收命令

```powershell
python -m pytest tests/test_portfolio_book_service.py tests/test_portfolio_book_api.py tests/test_fastapi_app.py -q --basetemp .pytest_tmp_ds007 -p no:cacheprovider
```

完成条件：OpenAPI 中可见上述路由；临时库往返通过；现有 API 不变；全量测试通过。

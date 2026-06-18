# DS-001：个人账本 SQLite 地基

把本文件原样交给 DeepSeek。不要同时追加其他任务。

## 用户价值

OptiFolio 需要一个与市场数据分离的个人账本，使账户、产品、录入草稿和持仓快照可以安全保存。这个任务只建立数据库地基，不实现任何业务表。

## 背景

- 产品路线图：`docs/PRODUCT_VISION_AND_EXECUTION_PLAN.md`
- 个人账本不属于 FinData；FinData 只保存外部市场与参考数据。
- 默认真实数据库未来位于 `local/portfolio_book.sqlite`，该目录已被 Git 忽略。
- 测试必须使用 pytest 的 `tmp_path`，不得创建或修改真实本地数据库。
- 当前项目运行于 Windows；不要假设 POSIX 路径或 shell。

## 允许修改

- 新增 `src/core/portfolio_book_db.py`
- 新增 `tests/test_portfolio_book_db.py`

## 禁止修改

- `FinData/`
- `app.py`
- `src/api/`
- `src/services/`
- `src/core/database.py`
- `config/asset_registry.yaml`
- `local/` 中的任何真实文件
- 其他测试和文档

如果认为必须修改禁止区域，停止实现并在结果中说明原因，不要自行扩大范围。

## 输入与输出契约

在 `src/core/portfolio_book_db.py` 新增一个小型数据库入口，建议接口：

```python
class PortfolioBookDatabase:
    CURRENT_SCHEMA_VERSION = 1

    def __init__(self, path: str | Path | None = None): ...
    def initialize(self) -> None: ...
    def connect(self) -> sqlite3.Connection: ...
    def schema_version(self) -> int: ...
```

要求：

- 未传路径时，默认路径为项目根目录下 `local/portfolio_book.sqlite`；
- 构造对象或 import 模块时不得创建文件；
- 只有显式调用 `initialize()` 才创建父目录和数据库；
- 使用 Python 标准库 `sqlite3`，不增加依赖；
- 初始化创建一个保存 schema version 的元数据表；
- 重复初始化必须幂等；
- 连接必须启用 foreign keys；
- 连接使用 row factory，使查询结果可按列名读取；
- 如果数据库 schema version 高于当前代码版本，抛出明确异常；
- 如果数据库没有版本或版本损坏，抛出明确异常，不猜测版本；
- 为未来升级保留私有 migration 分发点，但本任务不实现业务迁移。

异常可以使用本模块内定义的少量明确异常类型，例如：

```python
PortfolioBookError
UnsupportedSchemaVersionError
InvalidSchemaMetadataError
```

## 明确非目标

- 不创建 account、product、position、cashflow 等业务表；
- 不迁移现有 YAML 或 Parquet ledger；
- 不做 repository、service、API 或 UI；
- 不实现备份恢复；
- 不引入 ORM；
- 不抽象成通用数据库框架。

## 工程验收

测试至少覆盖：

1. import 和构造对象不会创建数据库；
2. `initialize()` 在 `tmp_path` 中创建数据库和父目录；
3. 初始化后 schema version 等于 1；
4. 连续调用两次 `initialize()` 不报错、不重复写坏元数据；
5. foreign keys 已启用；
6. row factory 支持按列名访问；
7. 人工写入更高版本后，初始化或读取会明确拒绝；
8. 人工删除/破坏版本元数据后，明确报错；
9. 测试全过程不触碰 `local/portfolio_book.sqlite`。

运行：

```powershell
python -m pytest tests/test_portfolio_book_db.py -q --basetemp .pytest_tmp_ds001 -p no:cacheprovider
python tools/privacy_scan.py --strict --with-detect-secrets
```

## 金融与隐私验收

- 此模块只提供个人账本存储，不混入市场价格或 FinData 表；
- 不出现真实账户、金额、机构或产品信息；
- 不把默认数据库提交进 Git；
- 缺失或不支持的 schema 不得被静默当成空账本。

## 实现风格

- 保持模块小而直接；
- 不使用 `print()`；
- 不为未来业务表预建复杂抽象；
- 所有路径使用 `pathlib.Path`；
- 公共类和异常写简短 docstring。

## 最终汇报格式

```text
修改文件：
- ...

实现内容：
- ...

测试：
- 命令：...
- 结果：...

刻意未做：
- ...

疑问或风险：
- ...
```

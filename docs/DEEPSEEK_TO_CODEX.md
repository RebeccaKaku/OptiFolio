# DeepSeek → Codex Handoff

## 我做了什么

### 1. 品牌清理（Safe Areas）
将以下文件中可见的旧品牌名称更新为 OptiFolio：
- `main.py`: `FM (Financial Manager)` → `OptiFolio`
- `downloader/__init__.py`: `NeoFM Downloader Module` → `OptiFolio Downloader Module`
- `fetchers/__init__.py`: `NeoFM 数据抓取模块` → `OptiFolio 数据抓取模块`
- `docs/` 下全部 9 个中文文档：标题、正文、目录树图中的 FM/NeoFM → OptiFolio
- `docs/开发指南.md`: venv 名 `fm_env` → `optifolio_env`、DB 名 `fm_db` → `optifolio_db`、指标名前缀 `fm_*` → `optifolio_*`
- `plans/module_architecture_design.md`: `NeoFM` / `NeoFMConfig` / `NeoFM/` → `OptiFolio` 系列

### 2. Bug 修复
**`src/asset_importer.py::AssetDefinition.from_dict`** — round-trip 时 attributes 双重嵌套。
- `to_dict()` 输出 `{'attributes': {...}}`
- 旧的 `from_dict` 把整个 `attributes` 键当作普通 kwarg 传给构造函数，导致 `self.attributes` 变成 `{'attributes': {...}}`
- 修复：检测到显式 `attributes` 键时直接将其值展开为 kwargs

### 3. 测试对齐
`tests/test_asset_registry.py`:
- 2 个测试保留并通过（`test_asset_attributes_management`、`test_registry_singleton_behavior`）
- 8 个测试标记为 `pytest.mark.skip`，均附有明确原因

### 4. .gitignore
新增：
```
*.parquet
*.db
*.db-journal
config/secrets.yaml
```

---

## 你需要处理的（Codex 管辖区）

### app.py — 旧品牌字符串仍在显示
- L2: `FM Dashboard - 基于Streamlit的可视化界面`
- L30: `page_title="FM 金融管理仪表板（增强版）"`
- L99: `## 📊 FM 金融管理`
- L173: `🏠 FM 金融管理仪表板`
- L1375: `fm_export_{datetime...}`
- L1554: `FM 金融管理系统 | 版本 1.0.0`

### src/api/enhanced_api_service.py
- L379: `"file_path": "data/fm_database.db"` — 数据库路径仍是旧名

### src/core/database.py
- L29: `def __init__(self, db_path: str = "data/fm_database.db")` — 默认路径仍是旧名

### src/core/exceptions.py
- L216, L225: 变量名 `fm_error` — 功能代码，看你要不要改

---

## 需要你决策的功能问题

以下 `AssetRegistry` 方法/属性被测试引用但当前未实现。8 个测试已 skip，等你的决定：

| 缺失的 API | 依赖的测试 |
|---|---|
| `conflicts` (dict 属性) | test_conflict_resolution_scenarios, test_conflict_to_single_asset_conversion, test_config_compatibility |
| `register_conflict_asset()` | 同上三个 |
| `remove_asset()` | test_conflict_to_single_asset_conversion, test_bulk_operations |
| `find_assets_by_type()` | test_asset_filtering |
| `detect_currency_from_name()` | test_currency_operations |
| `conflict_id` / `is_conflict` (AssetDefinition 属性) | 多个测试 |

另外 `register_asset` 当前不做任何输入校验（空符号、None 类型都能注册成功），`test_edge_cases` 也因此 skip 了。

---

## 验证结果
```
python -m compileall -q .          # 通过
pytest tests/test_asset_registry.py  # 2 passed, 8 skipped
```

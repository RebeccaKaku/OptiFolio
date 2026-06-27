# OptiFolio Financial Semantics Dictionary

> **Purpose**: Each concept in this dictionary has exactly ONE definition in OptiFolio.  
> When code uses a term, it MUST match this definition. If a term appears in multiple  
> contexts with different meanings, document the difference explicitly.

---

## 1. Portfolio Data Concepts

### Holding (持仓)

- **金融定义**: 投资者在某一时点持有的某一资产的数量。Holding 不含市值——市值是 Valuation 的结果。
- **公式**: `Holding(asset_id, quantity)`
- **与 Position 的关系**: Holding × Price = Position value。Holding 是输入，Position 是估值输出。
- **存储位置**: `PortfolioServiceV2._holdings: Dict[str, float]` (asset_id → quantity)
- **来源**: `PortfolioBookDatabase` 的 confirmed snapshot batch

### Position (估值后持仓)

- **金融定义**: Holding 经过市场估值后得到的有价仓位。包含价格、币种、汇率、折算后价值。
- **公式**: `PositionValue = {asset_id, quantity, price, currency, fx_rate, value_base}`
- **不变量**: `value_base = quantity × price × fx_rate` (当 base_currency ≠ asset_currency 时)
- **代码位置**: `src/domain/models.py:124` (`PositionValue` dataclass)

### Snapshot (快照)

- **金融定义**: 某一时点 (as_of) 所有账户中所有产品的持仓记录集合。快照是"此刻我有什么"的完整记录。
- **代码位置**: `position_snapshots` 表 in `PortfolioBookDatabase`
- **与 Holding 的区别**: Snapshot 是一条数据库记录（包含 account_id, product_id, quantity, market_value, currency）。Holding 是聚合后的 `{asset_id: quantity}` 字典。

### Cash (现金)

- **金融定义**: 账户中以各币种持有的现金余额。不计入 positions，单独估值后加入 total_value。
- **公式**: `cash_value_in_base = amount × fx_rate(base_currency, cash_currency)`
- **存储**: `PortfolioServiceV2._cash: Dict[str, float]` (currency → amount)
- **注意**: 货币基金（如余额宝）是 position（有净值），不是 cash。尽管金融上类似现金，但会计上它是基金份额。

---

## 2. Valuation (估值)

### Asset Valuation

- **金融定义**: 对 portfolio 中每个 position 赋予市场价值 (mark-to-market) 的过程。
- **公式**: `total_value = Σ(quantity × price × fx_rate) + Σ(cash × fx_rate)`
- **价格选择**: 取 `date <= as_of` 的最新 close price，向前最多回溯 5 个交易日。
- **代码位置**: `src/core/valuation.py` (`ValuationEngine.value()`)

### Price Date (价格日期)

- **金融定义**: 实际使用的市场价格的交易日期。与 as_of (估值日期) 不同——当 as_of 日无交易时，price_date < as_of。
- **示例**: as_of=2026-06-20 (周六)，price_date=2026-06-18 (最近交易日)
- **代码位置**: `PositionValue.price_date`

### Stale Days (陈旧天数)

- **金融定义**: `as_of - price_date` 的天数。表示估值依赖的价格有多"旧"。
- **金融含义**: stale_days > 3 时，估值可靠性显著下降；> 7 时，应向前端发出警告。
- **代码位置**: `PositionValue.stale_days`, `ValuationResult.stale_days`

### Valuation Quality

- **CONFIRMED**: 经人工或权威来源确认的价格。最高可靠性。
  - 来源: 用户手动录入、银行对账单确认
- **REPORTED**: 第三方报告但未经确认的价格。
  - 来源: akshare 爬取、yfinance 返回
- **ESTIMATED**: 通过插值、前值结转或代理指标推算的价格。
  - 来源: 无交易日的向前回溯、线性插值
- **UNKNOWN**: 完全无法获取可靠价格。
  - 典型场景: 银行理财无二级市场报价
- **代码位置**: `optifolio_contracts/quality.py` (`ValuationQuality` enum)

### Valuation Freshness

- **CURRENT**: 价格日期与估值日期一致 (同一交易日)。
- **STALE**: 价格日期早于估值日期，但仍在可接受范围内 (≤5 交易日)。
- **UNKNOWN**: 无法确定价格日期。
- **代码位置**: `optifolio_contracts/quality.py` (`ValuationFreshness` enum)

---

## 3. Exposure (敞口分析)

### Portfolio Exposure

- **金融定义**: 将 portfolio 总价值按某一维度分解为各 bucket 的占比。Level 0 = 仅基于产品标签，不做穿透 (look-through)。
- **维度**:
  - `asset_class`: 资产大类 (equity, fixed_income, cash, alternative)
  - `currency`: 持仓币种
- **公式**: `ExposureItem = {bucket, value, pct = value / total_value}`
- **代码位置**: `src/analytics/exposure.py` (`ExposureAnalyzer`)

### Asset Class (资产大类)

OptiFolio 使用 4 个大类：
| Bucket | 包含的资产类型 | 金融含义 |
|--------|---------------|---------|
| `equity` | us_equity, cn_stock, cn_fund (权益/混合型), cn_fund_etf | 承担企业权益风险 |
| `fixed_income` | cn_fund_bond, 债券型基金 | 承担利率和信用风险 |
| `cash` | cn_money_market_fund, deposit, 货币基金 | 近似现金等价物 |
| `alternative` | bank_wmp, crypto | 非标准化收益风险结构 |

- **分类依据**: 爬虫返回的 `fund_type_raw` 字段（如"货币型-普通货币"→ cash，"指数型-股票"→ equity），不是代码猜测。

---

## 4. Performance (业绩)

### Return Status (收益率可用性)

- **available**: 两个确认快照之间覆盖完整，可以做有意义的收益计算。
- **estimated**: 覆盖不完整（部分账户未录入），收益是估算值。
- **unavailable**: 无前一个确认快照可供比较，或数据不足以计算收益。

### Reconciliation Identity (对账恒等式)

```
closing_value - opening_value =
    external_net_flow
  + investment_income (interest + dividend + coupon)
  + fees_taxes (fee + tax)
  + market_change (residual)
  + fx_effect
  + unclassified_change (coverage incomplete 时)
```

- **market_change**: 当 coverage=complete 时的残差项，代表市场价格变动产生的资本利得/损失。
- **unclassified_change**: 当 coverage=partial 时，无法解释的变化全归入此项。
- **代码位置**: `src/analytics/reconciliation.py`

### Return Method

- **当前实现**: 简单期初期末差 + 现金流调整。
- **尚未实现**: Modified Dietz (按日加权现金流) 或 True TWR (子期链式)。
- **代码位置**: `src/analytics/reconciliation.py`

---

## 5. Currency & FX

### Base Currency vs Reporting Currency

- **base_currency**: 估值计算使用的目标货币。portfolio 中所有 position 和 cash 都转换为此货币后加总。
- **reporting_currency**: 前端展示使用的货币。通常与 base_currency 一致。
- **不变量**: valuation 内部所有计算使用 base_currency，只有最终展示时才可能转换为 reporting_currency。

### FX Rate (汇率)

- **金融定义**: 一单位 `from_currency` 可兑换多少单位 `to_currency`。
- **来源优先级**:
  1. `MarketDataRepository` (存储的历史汇率，按日期匹配)
  2. `CurrencyFetcher` (yfinance 实时汇率)
  3. 硬编码 fallback 表 (USD/CNY=7.2, EUR/USD=1.1, 等)
- **时点规则**: FX rate 的 as_of 必须与价格 price_date 一致，否则产生时点错配。

---

## 6. Data Concepts

### asset_type (资产类型标签)

- **定义**: 在 `asset_registry.yaml` 和 Fetcher Registry 中使用的资产分类标签。决定用哪个 fetcher 抓数据。
- **格式**: 小写字母 + 下划线 (如 `cn_stock`, `us_equity`, `cn_fund`)
- **枚举**: 见 `packages/findata/findata/adapters/__init__.py` FETCHER_REGISTRY

### product_type (产品类型)

- **定义**: 在 `PortfolioBookDatabase.products` 表中存储的产品分类。用于业务逻辑（费率、流动性、风险）。
- **值**: `deposit`, `money_fund`, `bond_fund`, `mixed_fund`, `bank_wmp`, `fx`, `structured_deposit`
- **与 asset_type 的关系**: product_type 是面向业务的产品分类，asset_type 是面向数据的技术分类。两者通过 `PortfolioServiceV2._map_asset_type_to_product_type()` 映射。

### asset_id (资产标识符)

- **格式约定**:
  - 美股: 大写 ticker (`AAPL`, `QQQ`)
  - A 股: 6 位数字代码 (`600519`, `000001`) 或带前缀 (`sh600519`, `sz000001`)
  - 基金: 6 位数字代码 (`510300`, `005827`)
  - 银行理财: WMP 代码 (`GRSDR260056`)
  - 汇率: `FX_{FROM}{TO}` (`FX_USDCNY`)
- **归一化**: 代码中通过 `optifolio_contracts.symbols.normalize_cn_symbol()` 统一处理前缀。旧的 `src/core/symbols.py` 已于 2026-06-23 删除。

---

## 7. Time Concepts

### as_of (估值时点)

- **金融定义**: 估值所针对的目标日期。"我想知道这一天我的 portfolio 值多少钱"。
- **惯例**: 如果 as_of 日无交易，使用最近的前一交易日价格。

### price_date (价格日期)

- **金融定义**: 实际使用的市场价格对应的交易日。
- **不变量**: `price_date <= as_of`

### effective_date (生效日期)

- **金融定义**: 公司行动（分红、拆股）或现金流的生效日期。
- **用途**: 在估值回溯时需要根据 effective_date 判断是否已应用某项调整。

### known_at (知悉日期)

- **金融定义**: 数据被系统获取或记录的日期。用于区分"数据何时发生"vs"我们何时知道"。
- **用途**: 防止前瞻偏差——不能使用 known_at 之后发生的数据。

---

## 8. Coverage (快照覆盖度)

### Coverage Level

- **complete**: 账户中所有产品均已确认录入。可用于收益率计算。
- **partial**: 部分产品已录入，但未完整覆盖。收益率仅供参考。
- **empty**: 确认账户无余额。计入覆盖统计但不产生持仓。
- **代码位置**: `src/analytics/reconciliation.py` (`CoverageLevel` enum)

---

## 9. Data Source Priority (数据源优先级)

持仓加载的优先级链:
1. `PortfolioBookDatabase` — 最新确认快照批次 (canonical)
2. 无 confirmed SQLite batch 时必须显式报错，不再读取静态组合文件

采用条件: book batch 中 >50% 的持仓有可用市价数据。否则回退 YAML（避免全部 WMP 导致 422）。

价格获取的优先级链:
1. `MarketDataRepository` (Parquet/DuckDB 缓存) — fast path
2. `Orchestrator.dispatch()` (akshare/yfinance 实时抓取) — live path
3. `NoPriceDataError` — 无可用价格时触发优雅降级

---

## Revision History

| Date | Version | Changes |
|------|---------|---------|
| 2026-06-23 | 1.1 | Updated code locations for FinData → packages migration |

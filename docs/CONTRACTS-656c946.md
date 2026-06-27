# OptiFolio Data Contracts

> **Purpose**: Field-level specification for every core data structure.  
> **Convention**: `T?` = nullable, `T[]` = list, `Dict[K,V]` = dict. All dates are ISO 8601 strings in transit, `date` objects in memory.
>
> **Architecture note (2026-06-28):** Fetcher and canonical-store contracts now
> live in the independent `RebeccaKaku/FinDataProvider` repository. OptiFolio
> consumes authenticated HTTP v1 envelopes through
> `src/infrastructure/market_data_client.py`; it does not import provider code.

---

## FinDataProvider response envelope

**Location**: external FinDataProvider `/v1/*`; decoded by
`src/infrastructure/market_data_client.py`.

| Field | Type | Nullable | Meaning | Invariants |
|-------|------|----------|---------|------------|
| `schema_version` | `str` | no | Provider API schema version | Currently `"1.0"` |
| `request_id` | `str` | no | Request correlation ID | UUID |
| `as_of` | `str` | no | Response production time | UTC ISO 8601 |
| `freshness` | `str` | no | Stored/derived/provider status | Never inferred by OptiFolio |
| `refresh_pending` | `bool` | no | Async ingestion was requested | Does not mean data is already available |
| `data` | `Any` | yes | Endpoint payload | JSON contains `null`, never `NaN`/Infinity |

---

## PositionValue

**Location**: `src/domain/models.py:124`  
**金融语义**: 一个持仓在估值后的结果。从 Holding (数量) 经过价格和汇率折算得到。

| Field | Type | Nullable | Meaning | Invariants | Example |
|-------|------|----------|---------|------------|---------|
| `asset_id` | `str` | no | 资产标识符 | 与 holdings 中的 key 一致 | `"510300"` |
| `quantity` | `float` | no | 持仓数量 (shares/units) | > 0 | `250.0` |
| `price` | `float` | no | 单位价格 (close) | > 0 | `4.984` |
| `currency` | `str` | no | 资产原生币种 | ISO 4217 | `"CNY"` |
| `fx_rate` | `float` | no | 折算为 base_currency 的汇率 | > 0; 同币种=1.0 | `1.0` |
| `value_base` | `float` | no | 折算后的市值 | = quantity × price × fx_rate | `1246.0` |
| `price_date` | `date` | yes | 实际价格对应的交易日 | ≤ as_of | `2026-06-18` |
| `stale_days` | `int` | no | 价格陈旧天数 | = (as_of - price_date).days; ≥ 0 | `2` |

---

## CashHolding

**Location**: `src/domain/models.py:143`  
**金融语义**: 一个币种的现金余额在估值后的结果。

| Field | Type | Nullable | Meaning | Invariants | Example |
|-------|------|----------|---------|------------|---------|
| `currency` | `str` | no | 现金币种 | ISO 4217 | `"USD"` |
| `amount` | `float` | no | 原币金额 | ≥ 0 | `5000.0` |
| `fx_rate` | `float` | no | 折算汇率 | > 0 | `7.2` |
| `value_base` | `float` | no | 折算后金额 | = amount × fx_rate | `36000.0` |

---

## ValuationResult (domain version)

**Location**: `src/domain/models.py:156`  
**金融语义**: 一次完整的 portfolio 估值输出。包含所有持仓、现金、汇率的估值明细。  
**⚠️ 注意**: 项目中有两个同名 `ValuationResult`。此为 domain 版（portfolio 级）。另一个在 `src/core/book_valuation.py`（单资产级）。Phase 3 将合并。

| Field | Type | Nullable | Meaning | Invariants | Example |
|-------|------|----------|---------|------------|---------|
| `as_of` | `date` | no | 估值目标日期 | — | `2026-06-20` |
| `total_value` | `float` | no | 总市值 | = holdings_value + cash_value | `1109310.12` |
| `holdings_value` | `float` | no | 持仓市值合计 | = Σ positions[].value_base | `1055390.12` |
| `cash_value` | `float` | no | 现金市值合计 | = Σ cash_breakdown[].value_base | `53920.0` |
| `base_currency` | `str` | no | 估值基础货币 | ISO 4217 | `"CNY"` |
| `positions` | `Dict[str, PositionValue]` | no | 持仓明细 | key = asset_id | `{"510300":...}` |
| `cash_breakdown` | `Dict[str, CashHolding]` | no | 现金明细 | key = currency | `{"USD":...}` |
| `fx_rates` | `Dict[str, float]` | no | 使用的汇率表 | key = currency code | `{"USD":7.2}` |
| `price_date` | `date` | yes | 使用的价格日期 | 最旧的 position price_date | `2026-06-18` |
| `stale_days` | `int` | yes | 全局陈旧天数 | 最大的 position stale_days | `2` |
| `corporate_action_adjustments` | `float` | no | 公司行动调整额 | 当前为 0（功能未接入） | `0.0` |
| `fee_adjustments` | `float` | no | 费用调整额 | 当前为 0 | `0.0` |

---

## ValuationResult (book version)

**Location**: `src/core/book_valuation.py:53`  
**金融语义**: 单个资产在某一估值方法下的估值结果。用于 priority-based 估值引擎（best-candidate selection）。  
**⚠️ 将在 Phase 3 与 domain 版合并。**

| Field | Type | Nullable | Meaning | Invariants | Example |
|-------|------|----------|---------|------------|---------|
| `amount` | `float` | yes | 估值金额 | — | `1246.0` |
| `currency` | `str` | no | 币种 | ISO 4217 | `"CNY"` |
| `valuation_date` | `date` | yes | 估值所用数据日期 | — | `2026-06-18` |
| `known_at` | `date` | yes | 数据被记录的日期 | — | `2026-06-19` |
| `source_type` | `str` | no | 估值源类型 | `"manual"`/`"public_nav"`/`"market_price"` | `"manual"` |
| `source_id` | `str` | no | 估值源标识 | — | `"batch_xxx"` |
| `quality` | `ValuationQuality` | no | 数据质量等级 | see GLOSSARY | `REPORTED` |
| `freshness` | `ValuationFreshness` | no | 数据时效性 | see GLOSSARY | `CURRENT` |
| `is_estimate` | `bool` | no | 是否为估算值 | True when quality≠CONFIRMED | `False` |
| `age_days` | `int` | no | 数据年龄 (天) | — | `2` |
| `warnings` | `List[str]` | no | 警告信息 | — | `["price is stale"]` |

---

## ExposureItem

**Location**: `src/analytics/exposure.py:7`  
**金融语义**: 一个敞口分组的汇总数据。

| Field | Type | Nullable | Meaning | Invariants | Example |
|-------|------|----------|---------|------------|---------|
| `dimension` | `str` | no | 分解维度 | `"asset_class"` / `"currency"` | `"asset_class"` |
| `bucket` | `str` | no | 分组标签 | — | `"equity"` |
| `value` | `float` | no | 分组总值 | 所有该组 position 的 value_base 之和 | `1055390.12` |
| `pct` | `float` | no | 占比 | = value / total_value; 0 ≤ pct ≤ 1 | `0.951` |
| `asset_ids` | `List[str]` | no | 该组包含的资产 | — | `["QQQ","AAPL","510300"]` |

---

## ExposureReport

**Location**: `src/analytics/exposure.py:16`  
**金融语义**: 一次完整的敞口分析报告。

| Field | Type | Nullable | Meaning | Invariants | Example |
|-------|------|----------|---------|------------|---------|
| `as_of` | `str` | no | 分析时点 | ISO 8601 | `"2026-06-20T15:48:00"` |
| `total_value` | `float` | no | portfolio 总价值 | = ValuationResult.total_value | `1109310.12` |
| `by_asset_class` | `List[ExposureItem]` | no | 按资产大类分解 | Σ pct = 1.0 | `[...]` |
| `by_currency` | `List[ExposureItem]` | no | 按币种分解 | Σ pct = 1.0 | `[...]` |

---

## PositionInput (reconciliation engine)

**Location**: `src/analytics/reconciliation.py`  
**金融语义**: 一个快照中某持仓的对账输入值（已转换为 reporting currency）。

| Field | Type | Nullable | Meaning | Invariants | Example |
|-------|------|----------|---------|------------|---------|
| `account_id` | `str` | no | 所属账户 | — | `"bosc_wm"` |
| `product_id` | `str` | no | 产品标识 | — | `"510300"` |
| `currency` | `str` | no | 币种 | 已转换为 reporting_currency | `"CNY"` |
| `market_value` | `Decimal` | yes | 市值 | ≥ 0 | `1246.0` |
| `quantity` | `Decimal` | yes | 数量 | — | `250.0` |

---

## CashflowInput (reconciliation engine)

**Location**: `src/analytics/reconciliation.py`  
**金融语义**: 两期之间的现金流事件（已转换为 reporting currency）。

| Field | Type | Nullable | Meaning | Invariants | Example |
|-------|------|----------|---------|------------|---------|
| `event_id` | `str` | no | 现金流事件 ID | — | `"cf_001"` |
| `event_type` | `str` | no | 类型 | `"contribution"`/`"withdrawal"`/`"dividend"`/`"fee"` | `"contribution"` |
| `account_id` | `str` | no | 所属账户 | — | `"bosc_wm"` |
| `amount` | `Decimal` | no | 金额 | contribution > 0; withdrawal < 0 | `5000.0` |
| `currency` | `str` | no | 币种 | 已转换 | `"CNY"` |
| `effective_date` | `date` | no | 生效日期 | 在 prev.as_of 和 curr.as_of 之间 | `2026-06-15` |

---

## SnapshotInput (reconciliation engine)

**Location**: `src/analytics/reconciliation.py`  
**金融语义**: 一个时点的完整快照（所有持仓的汇总）。

| Field | Type | Nullable | Meaning | Invariants | Example |
|-------|------|----------|---------|------------|---------|
| `batch_id` | `str` | no | 快照批次 ID | — | `"manual-2026-06-19-xxx"` |
| `as_of` | `date` | no | 快照日期 | — | `2026-06-19` |
| `status` | `str` | no | 状态 | `"draft"`/`"confirmed"` | `"confirmed"` |
| `account_coverage` | `Dict[str, CoverageLevel]` | no | 每个账户的覆盖度 | — | `{"bosc_wm":COMPLETE}` |
| `positions` | `List[PositionInput]` | no | 持仓列表 | — | `[...]` |

---

## ValuationCandidate

**Location**: `src/core/book_valuation.py:31`  
**金融语义**: 一个可用于估值的候选数据源。估值引擎从中选择最优者。

| Field | Type | Nullable | Meaning | Invariants | Example |
|-------|------|----------|---------|------------|---------|
| `amount` | `float` | yes | 直接金额 | 可直接使用 | `12460.0` |
| `price` | `float` | yes | 单价 | 需 × quantity | `4.984` |
| `quantity` | `float` | yes | 数量 | 需 × price | `250.0` |
| `currency` | `str` | no | 币种 | — | `"CNY"` |
| `effective_date` | `date` | yes | 生效日期 | — | `2026-06-18` |
| `known_at` | `date` | yes | 知悉日期 | — | `2026-06-19` |
| `source_id` | `str` | no | 来源标识 | — | `"batch_xxx"` |
| `source_type` | `str` | no | 来源类型 | — | `"market_price"` |
| `quality` | `ValuationQuality` | no | 质量等级 | — | `REPORTED` |

---

## ProductDefinition

**Location**: `src/domain/products.py:10`  
**金融语义**: 一个金融产品的完整定义。来自 registry 或数据库。

| Field | Type | Nullable | Meaning | Invariants | Example |
|-------|------|----------|---------|------------|---------|
| `product_id` | `str` | no | 产品唯一标识 | — | `"510300"` |
| `name` | `str` | no | 产品名称 | — | `"沪深300ETF"` |
| `product_type` | `str` | no | 产品类型 | 7 types: deposit/money_fund/bond_fund/mixed_fund/bank_wmp/fx/structured_deposit | `"index_fund"` |
| `issuer` | `str` | yes | 发行方 | — | `"华泰柏瑞"` |
| `manager` | `str` | yes | 管理人 | — | `"华泰柏瑞基金"` |
| `currency` | `str` | no | 产品币种 | ISO 4217 | `"CNY"` |
| `risk_level` | `str` | yes | 风险等级 | — | `"R4"` |
| `liquidity_type` | `str` | yes | 流动性类型 | — | `"T+1"` |
| `fee_policy_id` | `str` | yes | 费率模板 ID | — | `"etf_standard"` |
| `benchmark_id` | `str` | yes | 基准 ID | — | `"000300"` |
| `primary_instrument_id` | `str` | yes | 主工具 ID | 用于市价获取 | `"510300"` |
| `data_source` | `str` | no | 数据来源 | — | `"akshare"` |
| `metadata` | `Dict` | no | 扩展元数据 | contains fund_type_raw etc. | `{"fund_type_raw":"指数型-股票"}` |

---

## Revision History

| Date | Version | Changes |
|------|---------|---------|
| 2026-06-20 | 1.0 | Initial contracts for 10 core data structures |

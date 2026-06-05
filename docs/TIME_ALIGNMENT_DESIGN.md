# 全球市场时间对齐设计方案

**日期**: 2026-06-03
**状态**: 设计阶段，待实施

---

## 1. 问题陈述

OptiFolio 持有跨时区资产（美股、A股、港股、加密货币），但当前系统**不存在任何时间对齐机制**。

### 1.1 核心矛盾

```
美股收盘: 周一 16:00 EST (UTC-5)
         = 周一 21:00 UTC
         = 周二 05:00 北京时间 (UTC+8)

A股收盘: 周二 15:00 CST (UTC+8)
         = 周二 07:00 UTC
         = 周二 02:00 EST
```

**问题：当你对包含美股+A股的组合调用 `value_on(周二)` 时，你应该得到什么？**

- 美股周一收盘价？✅（北京时间周二凌晨已产生，周二全天都可用）
- A股周二收盘价？❓（如果你在周二上午 10 点查，A股还没收盘）

答案取决于 "周二" 的**截止时间**是什么——是周二 00:00？周二 15:00？还是周二 23:59？

### 1.2 当前代码做了什么

**`src/data_foundation/schemas.py:84`** — 所有时间信息在此被无条件抹除：

```python
df["date"] = pd.to_datetime(df["date"], errors="raise").dt.tz_localize(None)
```

**各 fetcher 的时区处理相互矛盾：**

| Fetcher | 策略 | 结果（周一美股收盘为例） |
|---------|------|--------------------------|
| `yahoo_fetcher.py` | UTC 转换 → 剥离 | naive `2024-01-08 21:00:00` |
| `us_equity.py` (legacy) | 直接剥离 | naive `2024-01-08 00:00:00` |
| `cn_fund.py` | 无时区 | naive `2024-01-08` |
| `cn_stock.py` | 无时区 | naive `2024-01-08` |
| `icbc.py / boc.py / bosc.py` | 无时区 | naive `2024-01-08` |

**同一个美股收盘事件，在系统中存在两种不同的时间戳** — 差了一天。

## 2. 设计原则

### 2.1 存储：交易日历日期（date-only）

**日线数据的正确抽象不是"时间点"而是"交易日"。**

- "AAPL 周一收盘价" 应存储为 `date = 2024-01-08`（周一），不管你在哪个时区
- "510300 周二收盘价" 应存储为 `date = 2024-01-09`（周二）
- 这个 date 是**该交易所当地日历的日期**，而不是 UTC 日期

**规则：每个资产的每日价格以其交易所当地的交易日期标识。**

### 2.2 查询：截止时间语义

`value_on(T, cutoff=EXCHANGE_CLOSE)` 的语义是：

> 使用交易所当地时间 `<= T` 且已收盘的最新价格

不同交易所的收盘时间不同：
- NYSE: T 日 16:00 EST
- SSE: T 日 15:00 CST
- Crypto: T 日 23:59 UTC（永续市场）

这意味着：北京时间周二上午 10 点调用 `value_on(周二)`：
- 美股周一收盘价 ✅ 可用（已过去 ~29 小时）
- A股周二收盘价 ❌ 不可用（距离收盘还有 5 小时）

### 2.3 可知道性（Knowability）

防止 look-ahead bias 的关键约束：

> 价格为 $P_{t}$ 在时刻 $\tau$ 可用于估值的条件是：交易所当地时间的 $t$ 日已收盘 AND $\tau \ge$ 收盘时刻

这个约束在回测中极其重要，在实时估值中也需要。

## 3. 方案设计

### 3.1 Canonical Schema 变更

**`src/data_foundation/schemas.py`** — `CANONICAL_MARKET_COLUMNS` 新增一列：

```python
CANONICAL_MARKET_COLUMNS = [
    "asset_id",
    "date",           # ← 改为: 交易所当地的纯日历日期 (date-only, 无时间)
    "exchange_date",  # ← 新增: 同 date，语义明确的别名
    "open", "high", "low", "close", "adj_close", "volume",
    "currency",
    "source",
    "timezone",       # ← 新增: 交易所时区，如 "America/New_York"
]
```

`normalize_market_frame()` 的关键变更：

```python
# 旧: 无条件剥离时区
df["date"] = pd.to_datetime(df["date"], errors="raise").dt.tz_localize(None)

# 新: 转换为交易所当地日期
df["date"] = _to_exchange_date(df["date"], timezone)
# 例: 2024-01-08T21:00:00+00:00 → date(2024, 1, 8) if tz=America/New_York
# 例: 2024-01-08T21:00:00+00:00 → date(2024, 1, 9) if tz=Asia/Shanghai
```

### 3.2 交易所日历注册表

**新文件 `src/core/calendars.py`**：

```python
@dataclass(frozen=True)
class ExchangeCalendar:
    name: str                    # "NYSE", "SSE", "SEHK"
    timezone: str                # "America/New_York", "Asia/Shanghai"
    close_time: time             # 收盘时间（当地时间）
    holidays: Set[date]          # 假期列表
    business_days: Callable      # 判断是否为交易日

EXCHANGE_CALENDARS = {
    "us_equity": ExchangeCalendar("NYSE", "America/New_York", time(16, 0)),
    "cn_stock":  ExchangeCalendar("SSE", "Asia/Shanghai", time(15, 0)),
    "cn_fund":   ExchangeCalendar("SSE", "Asia/Shanghai", time(15, 0)),
    "crypto":    ExchangeCalendar("CRYPTO", "UTC", time(23, 59, 59)),
    "forex":     ExchangeCalendar("FOREX", "UTC", time(23, 59, 59)),
}

# 资产 → 日历映射（从 asset_registry 的 asset_type 派生）
def get_calendar(asset_id: str) -> ExchangeCalendar: ...
```

### 3.3 Fetcher 标准化

所有 fetcher 需要在返回数据前统一为交易所当地日期：

```python
# 每个 fetcher 实现此方法
def _normalize_dates(self, df: pd.DataFrame) -> pd.DataFrame:
    """Convert any datetime index to exchange-local date-only."""
    tz = self.exchange_timezone  # 每个 fetcher 声明自己对应的交易所时区
    if isinstance(df.index, pd.DatetimeIndex):
        if df.index.tz is None:
            # 如果不知道时区，假设是交易所当地时间（向后兼容）
            df.index = df.index.tz_localize(tz)
        else:
            # 先转到交易所时区，再取日期
            df.index = df.index.tz_convert(tz)
        # 只保留日期部分
        df.index = df.index.normalize()  # 或 .date
    return df
```

这消除了当前 `yahoo_fetcher.py`（UTC 转换后剥离）和 `us_equity.py`（直接剥离）之间的不一致。

### 3.4 可知道性检查器

**`ValuationEngine.value()` 增强**：

```python
def value(self, holdings, cash, request: ValuationRequest) -> ValuationResult:
    """
    request.as_of: date — 估值参考日期
    request.cutoff: Optional[time] — 估值截止时间，默认为当日 23:59

    对于每个资产:
    1. 查询 date <= as_of 的最新价格
    2. 如果 price.date == as_of 且当前时刻还未到该交易所收盘:
       → 跳过此价格（尚未可知），回看前一个交易日
    """
```

这个"可知道性检查"对实时估值很重要，但对历史回测可以关闭（回测时所有价格都是已知的）。

### 3.5 跨市场时间对齐示例

```
组合: AAPL (NYSE) + 510300 (SSE) + BTC (crypto)
估值日: 2024-01-09 (周二)
估值时刻: 北京时间 10:00
```

| 资产 | 交易日期 | 收盘时刻 | 10:00 BJ 时可知? | 用于估值? |
|------|----------|----------|-------------------|-----------|
| AAPL | 01-08 (周一) | 01-08 16:00 EST | ✅ (29小时前) | ✅ |
| 510300 | 01-09 (周二) | 01-09 15:00 CST | ❌ (还有5小时) | ❌ → 回退到 01-08 |
| BTC | 01-09 (周二) | 01-09 23:59 UTC | ❌ (还有14小时) | ❌ → 回退到 01-08 23:59 |

**结果**：周二上午的组合净值使用 AAPL 周一收盘 + 510300 周一收盘 + BTC 周一 UTC 午夜价。

同一天下午 16:00 再查：510300 已收盘，所以会使用周二收盘价。
BTC 仍用前一日价（UTC 23:59 还没到）。

## 4. 实施计划

### Phase A: 基础设施（1 天）

| # | 任务 | 文件 |
|---|------|------|
| A1 | 创建 `src/core/calendars.py` — ExchangeCalendar 注册表 | 新建 |
| A2 | 扩展 `CANONICAL_MARKET_COLUMNS` 加 `timezone` 列 | `schemas.py` |
| A3 | `normalize_market_frame()` 改为交易所当地日期转换 | `schemas.py` |
| A4 | `validate_market_frame()` 加 timezone 字段校验 | `schemas.py` |

### Phase B: Fetcher 改造（1-2 天）

| # | 任务 |
|---|------|
| B1 | `yahoo_fetcher.py` — UTC→交易所当地日期（而非 UTC→剥离） |
| B2 | `cn_fund.py` — 明确声明 Asia/Shanghai 时区 |
| B3 | `cn_stock.py` — 同 B2 |
| B4 | `icbc.py / boc.py / bosc.py` — 银行理财数据全是纯日期，无需改动 |
| B5 | `crypto_fetcher.py` — Unix ms → UTC → 当地日期 |
| B6 | 废弃 `us_equity.py` 的直接剥离策略，统一到 yahoo_fetcher 的路径 |

### Phase C: 估值引擎增强（1 天）

| # | 任务 |
|---|------|
| C1 | `ValuationEngine` 支持 `cutoff` 参数（可知道性检查） |
| C2 | `ValuationEngine._get_asset_calendar()` 从 asset_registry 查时区 |
| C3 | 多日历回看：当某交易所当天未收盘时，回退到该交易所前一交易日 |

### Phase D: 回测加固（0.5 天）

| # | 任务 |
|---|------|
| D1 | `BacktestEngine` 支持多日历重采样 |
| D2 | 验证：跨市场回测不产生 look-ahead bias |

## 5. 对现有数据的影响

- **向后兼容**: 已存储的 tz-naive 数据默认假设为 UTC（或交易所当地时间），需要一次性迁移脚本
- **迁移脚本**: 读取 `market_prices.parquet`，根据 `source` 字段推断时区，重新计算 `date` 列
- **Parquet 格式**: Parquet 原生支持 date-only 类型（`DATE`），比 datetime 更紧凑

## 6. 参考资料

- `processor/aligner.py` — 已有的 `DataAligner` 包含正确的交易所日历概念，但未接入主流程
- `src/data_foundation/schemas.py:84` — 时区信息被抹除的关键位置
- `fetchers/yahoo_fetcher.py:84-86` — 两个不一致剥离策略之一
- `src/core/valuation.py:277` — 估值引擎的 naive 日期比较

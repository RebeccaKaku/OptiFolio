# NeoFM - 金融数据抓取框架

NeoFM 是一个统一的金融数据抓取框架，提供标准化的 API 接口，支持多种数据源的数据获取。

## 项目结构

```
NeoFM/
├── fetchers/                 # 数据抓取模块
│   ├── __init__.py          # 模块入口
│   ├── interfaces.py        # 核心接口定义
│   ├── crypto_fetcher.py    # 加密货币数据抓取
│   ├── yahoo_fetcher.py     # Yahoo Finance 数据抓取
│   └── cn_fund.py           # 中国公募基金数据抓取
├── api_checker/              # API 检测模块
│   ├── __init__.py          # 模块入口
│   ├── base.py              # 基类定义
│   ├── crypto_checker.py    # 加密货币 API 检测
│   ├── yahoo_checker.py     # Yahoo Finance API 检测
│   ├── akshare_checker.py   # Akshare API 检测
│   ├── runner.py            # 统一运行器
│   └── test_api_checker.py  # 测试脚本
└── README.md                 # 项目文档
```

## 安装依赖

```bash
# 核心依赖
pip install pandas

# 数据源依赖 (按需安装)
pip install ccxt          # 加密货币数据
pip install yfinance      # Yahoo Finance 数据
pip install akshare       # 中国金融数据
```

---

## Fetcher 模块 API 文档

### 核心接口: AsyncBaseFetcher

所有数据抓取器都继承自 `AsyncBaseFetcher`，遵循统一的接口规范。

```python
from fetchers import AsyncBaseFetcher

class AsyncBaseFetcher(ABC):
    @abstractmethod
    async def fetch(
        self, 
        symbol: str,           # 交易品种代码
        start_date: str,       # 开始日期 (YYYY-MM-DD)
        end_date: str,         # 结束日期 (YYYY-MM-DD)
        timeframe: str = '1d', # 时间周期
        exchange: Optional[str] = None,  # 交易所
        **kwargs
    ) -> pd.DataFrame:
        pass
```

### 返回数据格式

所有 `fetch()` 方法返回的 DataFrame 遵循以下规范：

| 字段 | 类型 | 说明 |
|------|------|------|
| **索引** | `pd.DatetimeIndex` | 名称必须为 `timestamp` |
| `open` | `float` | 开盘价 |
| `high` | `float` | 最高价 |
| `low` | `float` | 最低价 |
| `close` | `float` | 收盘价 |
| `volume` | `float` | 成交量 |

**示例输出:**

```
                           open      high       low     close    volume
timestamp                                                              
2024-01-01 00:00:00  42000.5  42500.0  41800.0  42300.0  12345.67
2024-01-02 00:00:00  42300.0  42800.0  42100.0  42650.0  13456.78
2024-01-03 00:00:00  42650.0  43000.0  42400.0  42800.0  14567.89
```

---

### CryptoFetcher - 加密货币数据

支持 Binance、OKX、Kraken 等主流交易所。

**初始化:**

```python
from fetchers import CryptoFetcher

# 默认使用 Binance
fetcher = CryptoFetcher()

# 指定交易所
fetcher = CryptoFetcher(exchange_id='okx')
```

**支持的 timeframe:**

| 参数值 | 说明 |
|--------|------|
| `1m` | 1分钟 |
| `5m` | 5分钟 |
| `15m` | 15分钟 |
| `1h` | 1小时 |
| `1d` | 1天 (默认) |
| `1w` | 1周 |
| `1M` | 1月 |

**使用示例:**

```python
import asyncio
from fetchers import CryptoFetcher

async def main():
    fetcher = CryptoFetcher(exchange_id='binance')
    
    df = await fetcher.fetch(
        symbol='BTC/USDT',
        start_date='2024-01-01',
        end_date='2024-01-31',
        timeframe='1d'
    )
    
    print(df.head())

asyncio.run(main())
```

**参数说明:**

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `symbol` | str | 是 | 交易对，如 `BTC/USDT` |
| `start_date` | str | 是 | 开始日期，格式 `YYYY-MM-DD` |
| `end_date` | str | 是 | 结束日期，格式 `YYYY-MM-DD` |
| `timeframe` | str | 否 | 时间周期，默认 `1d` |
| `exchange` | str | 否 | 覆盖默认交易所 |

---

### YahooFinanceFetcher - 美股/港股/ETF 数据

支持美股、港股、ETF、外汇和部分期货。

**初始化:**

```python
from fetchers import YahooFinanceFetcher

fetcher = YahooFinanceFetcher()
```

**支持的 timeframe:**

| 参数值 | 说明 |
|--------|------|
| `1m` | 1分钟 (仅最近7天) |
| `5m` | 5分钟 (仅最近60天) |
| `15m` | 15分钟 |
| `1h` | 1小时 |
| `1d` | 1天 (默认) |
| `1w` | 1周 |
| `1M` | 1月 |

**使用示例:**

```python
import asyncio
from fetchers import YahooFinanceFetcher

async def main():
    fetcher = YahooFinanceFetcher()
    
    # 美股
    df = await fetcher.fetch(
        symbol='AAPL',
        start_date='2024-01-01',
        end_date='2024-01-31'
    )
    
    # 港股 (通过 exchange 参数)
    df_hk = await fetcher.fetch(
        symbol='0700',
        start_date='2024-01-01',
        end_date='2024-01-31',
        exchange='HK'  # 自动添加 .HK 后缀
    )
    
    print(df.head())

asyncio.run(main())
```

**参数说明:**

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `symbol` | str | 是 | 股票代码 |
| `start_date` | str | 是 | 开始日期 |
| `end_date` | str | 是 | 结束日期 |
| `timeframe` | str | 否 | 时间周期，默认 `1d` |
| `exchange` | str | 否 | 交易所代码，如 `HK`、`LSE` |

---

### CnFundFetcher - 中国公募基金数据

支持场内ETF、场外公募基金、货币基金。

**初始化:**

```python
from fetchers import CnFundFetcher

# 使用默认缓存目录
fetcher = CnFundFetcher()

# 指定缓存目录
fetcher = CnFundFetcher(cache_dir='.cache')
```

**使用示例:**

```python
import asyncio
from fetchers import CnFundFetcher

async def main():
    fetcher = CnFundFetcher()
    
    # 抓取基金数据 (自动识别类型)
    df = await fetcher.fetch(
        symbol='000001',  # 基金代码
        start_date='2024-01-01',
        end_date='2024-01-31'
    )
    
    print(df.head())

asyncio.run(main())
```

**智能路由:**

`CnFundFetcher` 会根据基金类型自动选择数据源：

| 基金类型 | 数据来源 |
|----------|----------|
| 货币基金 | `ak.fund_money_fund_info_em()` |
| 场内ETF | `ak.fund_etf_hist_em()` |
| 场外公募 | `ak.fund_open_fund_info_em()` |

**参数说明:**

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `symbol` | str | 是 | 基金代码 |
| `start_date` | str | 是 | 开始日期 |
| `end_date` | str | 是 | 结束日期 |
| `timeframe` | str | 否 | 仅支持 `1d` (默认) |
| `exchange` | str | 否 | 基金数据不需要此参数 |

---

## API Checker 模块文档

API Checker 模块用于检测各数据源 API 的连通性，帮助排查网络问题。

### 快速使用

```python
from api_checker import run_check

# 同步方式运行检测
result = run_check()
```

### 异步使用

```python
import asyncio
from api_checker import quick_check

async def main():
    result = await quick_check()
    print(result)

asyncio.run(main())
```

### 自定义检测

```python
import asyncio
from api_checker import APICheckerRunner, CryptoAPIChecker

async def main():
    runner = APICheckerRunner(log_dir="logs")
    
    # 添加自定义检测器
    runner.add_checker(CryptoAPIChecker(exchanges=['binance', 'okx']))
    
    # 运行检测
    results = await runner.run_all()
    
    # 获取汇总
    summary = runner.get_summary()
    print(f"成功率: {summary['success_rate']*100:.1f}%")

asyncio.run(main())
```

### 检测结果格式

`CheckResult` 对象包含以下属性：

| 属性 | 类型 | 说明 |
|------|------|------|
| `name` | str | API 名称 |
| `status` | CheckStatus | 状态: `OK`, `FAIL`, `TIMEOUT`, `ERROR` |
| `latency_ms` | float | 响应延迟 (毫秒) |
| `message` | str | 详细信息 |
| `is_ok` | bool | 是否成功 |

**汇总数据格式:**

```python
{
    'timestamp': '2024-01-15T10:30:00',
    'total': 3,
    'success': 2,
    'failed': 1,
    'success_rate': 0.667,
    'results': [
        {
            'name': 'Crypto',
            'status': 'OK',
            'latency_ms': 245.0,
            'message': 'BTC/USDT: $42,300.00',
            'is_ok': True
        },
        # ...
    ]
}
```

### 命令行使用

```bash
# 运行默认检测
python -m api_checker.runner

# 指定交易所
python -m api_checker.runner binance,okx

# 指定日志目录
python -m api_checker.runner binance,okx ./my_logs
```

---

## 开发指南

### 添加新的 Fetcher

1. 创建新文件 `fetchers/new_fetcher.py`
2. 继承 `AsyncBaseFetcher`
3. 实现 `fetch()` 方法
4. 确保返回格式符合规范

```python
from fetchers import AsyncBaseFetcher
import pandas as pd
from typing import Optional

class NewFetcher(AsyncBaseFetcher):
    async def fetch(
        self, 
        symbol: str, 
        start_date: str, 
        end_date: str, 
        timeframe: str = '1d',
        exchange: Optional[str] = None,
        **kwargs
    ) -> pd.DataFrame:
        # 实现数据抓取逻辑
        df = pd.DataFrame(...)
        
        # 确保格式正确
        df.index.name = 'timestamp'
        df.columns = [c.lower() for c in df.columns]
        
        return df
```

### 添加新的 API Checker

1. 创建新文件 `api_checker/new_checker.py`
2. 继承 `APIChecker`
3. 实现 `check()` 方法

```python
from api_checker import APIChecker, CheckResult

class NewAPIChecker(APIChecker):
    async def check(self) -> CheckResult:
        try:
            # 执行检测
            with self._measure_time() as timer:
                # ... 检测逻辑 ...
                pass
            
            return self._create_success_result(
                timer.latency_ms,
                "Connection OK"
            )
        except Exception as e:
            return self._create_fail_result(
                CheckStatus.FAIL,
                str(e)
            )
```

---

## 许可证

MIT License

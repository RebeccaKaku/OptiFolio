"""
scripts/fetch_boc_metadata.py

为中银理财（BOCWM）所有活跃产品抓取元数据：
  - 成立日 (establishment_date)
  - 到期日 (maturity_date)
  - 起购金额 + 货币单位 (min_purchase / currency)
  - 下一开放申赎日 (next_open_date)
  - 产品说明书 PDF 链接 (prospectus_pdf_url / prospectus_pdf_title)

输出：config/boc_product_metadata.json
用法：python scripts/fetch_boc_metadata.py [--max N]
"""

import asyncio
import json
import re
import sys
import argparse
from datetime import datetime
from pathlib import Path
from typing import Optional

import httpx
import io

# Windows GBK 终端下强制 UTF-8 输出
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

# ──────────────────────────────────────────────
# 常量
# ──────────────────────────────────────────────
PRODUCT_LIST_URL     = "https://www.bocwm.cn/webApi/cms/product/queryStaticProducts"
OPEN_DATE_URL        = "https://www.bocwm.cn/webApi/cms/productOpenDate/getOpenDate"
INSTRUCTIONS_URL     = "https://www.bocwm.cn/webApi/cms/productDynamicPage/getProductInstructionsList"
DETAIL_BASE_URL      = "https://www.bocwm.cn"
PROSPECTUS_BASE_URL  = "https://www.bocwm.cn"   # PDF 路径前缀

OUTPUT_PATH = Path("config/boc_product_metadata.json")
CONCURRENCY = 10   # 同时并发的产品数

HEADERS = {
    "Content-Type": "application/json",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
}

# 货币文字 → ISO 代码
CURRENCY_MAP = {
    "人民币": "CNY",
    "元":     "CNY",
    "美元":   "USD",
    "港币":   "HKD",
    "港元":   "HKD",
    "欧元":   "EUR",
    "英镑":   "GBP",
    "日元":   "JPY",
    "澳元":   "AUD",
    "澳币":   "AUD",
}

# 产品名称关键词 → 货币（用于 HTML 解析失败时的回退）
NAME_CURRENCY_KEYWORDS: list = [
    ("美元", "USD"),
    ("USD",  "USD"),
    ("港元", "HKD"),
    ("港币", "HKD"),
    ("HKD",  "HKD"),
    ("澳元", "AUD"),
    ("澳币", "AUD"),
    ("AUD",  "AUD"),
    ("欧元", "EUR"),
    ("EUR",  "EUR"),
    ("英镑", "GBP"),
    ("GBP",  "GBP"),
    ("日元", "JPY"),
    ("JPY",  "JPY"),
]

def infer_currency_from_name(name: str) -> Optional[str]:
    """从产品名称关键词推断货币，兜底默认人民币"""
    if not name:
        return "CNY"
    for kw, iso in NAME_CURRENCY_KEYWORDS:
        if kw in name:
            return iso
    return "CNY"  # 默认人民币


# ──────────────────────────────────────────────
# Step 1：拉取全部产品列表（返回原始 row 列表）
# ──────────────────────────────────────────────
async def fetch_product_rows(client: httpx.AsyncClient) -> list:
    payload = {"pageNo": 1, "pageSize": 5000}
    resp = await client.post(PRODUCT_LIST_URL, json=payload, timeout=20)
    resp.raise_for_status()
    data = resp.json()
    if not data.get("result"):
        raise RuntimeError("queryStaticProducts returned result=false")
    rows = data.get("data", {}).get("rows", [])
    print(f"[BOC] 产品总数: {len(rows)}")
    return rows


# ──────────────────────────────────────────────
# Step 2a：解析详情页 HTML（静态字段）
# ──────────────────────────────────────────────
# 所有关键字段都被服务端硬编码在 HTML 的 .toprow 标签或 <script> 里

_TOPROW_RE = re.compile(
    r'<span[^>]*>([^<]+)：?</span>([^<]{0,200}?)(?:<|$)',
    re.S,
)

# 详情页 <script> 里也有一些字段被静态写入
_SCRIPT_CLR_RE  = re.compile(r"let clr\s*=\s*'(\d{4}-\d{2}-\d{2})'")   # 成立日
_SCRIPT_TERM_RE = re.compile(r"termkt\s*:\s*'([^']+)'")                   # 存续期
_SCRIPT_HOLD_RE = re.compile(r"shrtstHoldTerm\s*:\s*'([^']+)'")           # 最短持有期

# 真实 HTML 结构：<span>LABEL:</span>VALUE</div>
# 用通用匹配：<span>KEY:</span> 后面紧接文字直到 </div>
def _span_value(html: str, label: str) -> Optional[str]:
    """从 <span>label:</span>VALUE</div> 提取 VALUE，兼容半角/全角冒号"""
    for colon in (':', '\uff1a'):  # ASCII colon + Chinese full-width colon
        pattern = re.compile(
            re.escape(f'<span>{label}{colon}</span>') + r'([^<]+)',
            re.S,
        )
        m = pattern.search(html)
        if m:
            return m.group(1).strip()
    return None

def _extract_currency(amount_text: str, unit_text: str) -> Optional[str]:
    """从「1.00人民币元」或「1,000.00美元」提取 ISO 货币代码"""
    combined = (amount_text + unit_text).strip()
    for zh, iso in CURRENCY_MAP.items():
        if zh in combined:
            return iso
    return None

def parse_detail_html(html: str) -> dict:
    """从产品详情页 HTML 提取静态字段"""
    result: dict = {}

    # ① 从 <script> 提取成立日 / 存续期 / 最短持有期
    m = _SCRIPT_CLR_RE.search(html)
    if m:
        result["establishment_date"] = m.group(1)

    m = _SCRIPT_TERM_RE.search(html)
    if m:
        result["term"] = m.group(1)
    m = _SCRIPT_HOLD_RE.search(html)
    if m:
        result["min_hold_period"] = m.group(1)

    # ② 从 HTML <span>LABEL:</span>VALUE</div> 结构提取各字段

    # 成立日（补充，脚本里有时没有）
    if "establishment_date" not in result:
        val = _span_value(html, "成立日")
        if val and re.match(r'\d{4}-\d{2}-\d{2}', val):
            result["establishment_date"] = val[:10]

    # 到期日
    val = _span_value(html, "到期日")
    if val and re.match(r'\d{4}-\d{2}-\d{2}', val):
        result["maturity_date"] = val[:10]

    # 认购期
    val = _span_value(html, "认购期")
    if val:
        result["subscription_period"] = val.strip()

    # 起购金额 + 货币：值如 "1.00人民币元" 或 "1,000.00美元"
    val = _span_value(html, "起购金额")
    if val:
        # 提取数字部分
        num_m = re.match(r'([\d,\.]+)(.*)', val)
        if num_m:
            result["min_purchase_amount"] = num_m.group(1).replace(",", "")
            currency = _extract_currency(num_m.group(1), num_m.group(2))
            if currency:
                result["currency"] = currency

    return result


# ──────────────────────────────────────────────
# Step 2b：调 getOpenDate API
# ──────────────────────────────────────────────
async def fetch_open_date(client: httpx.AsyncClient, code: str) -> Optional[str]:
    try:
        resp = await client.get(OPEN_DATE_URL, params={"productCode": code}, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        if data.get("result"):
            val = data.get("data")
            return val if val and val != "-" else None
    except Exception:
        pass
    return None


# ──────────────────────────────────────────────
# Step 2c：调 getProductInstructionsList API → PDF 链接
# ──────────────────────────────────────────────
async def fetch_pdf_links(client: httpx.AsyncClient, code: str) -> list:
    """返回 [{"title": ..., "url": ..., "date": ...}, ...]"""
    try:
        resp = await client.get(INSTRUCTIONS_URL, params={"productCode": code}, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        if data.get("result"):
            items = data.get("data") or []
            pdfs = []
            for item in items:
                path = item.get("contentPath", "")
                full_url = PROSPECTUS_BASE_URL + path if path.startswith("/") else path
                pdfs.append({
                    "title":    item.get("title", ""),
                    "url":      full_url,
                    "date":     item.get("contentDatetime", ""),
                })
            return pdfs
    except Exception:
        pass
    return []


# ──────────────────────────────────────────────
# Step 3：整合单个产品的全部元数据
# ──────────────────────────────────────────────
async def enrich_product(
    client: httpx.AsyncClient,
    row: dict,
    semaphore: asyncio.Semaphore,
) -> dict:
    code        = row.get("productCode", "")
    detail_path = row.get("productDetailUrl", "")  # e.g. "/3/9634.html"

    # 基础信息（来自产品列表 API）
    meta = {
        "product_code":   code,
        "product_name":   row.get("productName"),
        "risk_level":     row.get("riskLevel"),
        "detail_url":     DETAIL_BASE_URL + "/html/1" + detail_path if detail_path else None,
        # releaseDate 有时从列表 API 就能拿到（已有净值的产品才有）
        "establishment_date": row.get("releaseDate") or None,
        "maturity_date":      None,
        "subscription_period": None,
        "min_purchase_amount": None,
        "currency":           None,
        "next_open_date":     None,
        "prospectus_pdfs":    [],
        "fetched_at":         datetime.now().isoformat(timespec="seconds"),
    }

    async with semaphore:
        # ── 详情页 HTML ──
        if detail_path:
            html_url = DETAIL_BASE_URL + "/html/1" + detail_path
            try:
                resp = await client.get(html_url, timeout=15)
                if resp.status_code == 200:
                    parsed = parse_detail_html(resp.text)
                    # 列表 API 的 releaseDate 优先（已确认正确）；HTML 提取作为补充
                    if not meta["establishment_date"]:
                        meta["establishment_date"] = parsed.get("establishment_date")
                    meta["maturity_date"]         = parsed.get("maturity_date")
                    meta["subscription_period"]   = parsed.get("subscription_period")
                    meta["min_purchase_amount"]   = parsed.get("min_purchase_amount")
                    meta["currency"]              = parsed.get("currency")
                    meta["term"]                  = parsed.get("term")
                    meta["min_hold_period"]       = parsed.get("min_hold_period")
            except Exception as e:
                meta["_html_error"] = str(e)

        # ── 货币回退：HTML 未能解析时用产品名称推断 ──
        if not meta["currency"]:
            meta["currency"] = infer_currency_from_name(meta.get("product_name") or "")
            meta["currency_source"] = "name_inference"
        else:
            meta["currency_source"] = "html_parsed"

        # ── 下一开放申赎日 ──
        meta["next_open_date"] = await fetch_open_date(client, code)

        # ── PDF 说明书链接 ──
        meta["prospectus_pdfs"] = await fetch_pdf_links(client, code)

    return meta


# ──────────────────────────────────────────────
# 主流程
# ──────────────────────────────────────────────
async def main(max_products: Optional[int] = None):
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    async with httpx.AsyncClient(headers=HEADERS, follow_redirects=True) as client:
        # 1. 拉产品列表
        rows = await fetch_product_rows(client)
        if max_products:
            rows = rows[:max_products]
            print(f"[BOC] 限制只处理前 {max_products} 个产品（调试模式）")

        # 2. 并发抓取每个产品的元数据
        semaphore = asyncio.Semaphore(CONCURRENCY)
        tasks = [enrich_product(client, row, semaphore) for row in rows]

        results = []
        done = 0
        total = len(tasks)
        for coro in asyncio.as_completed(tasks):
            result = await coro
            results.append(result)
            done += 1
            code = result.get("product_code", "?")
            est  = result.get("establishment_date") or "-"
            mat  = result.get("maturity_date") or "-"
            opn  = result.get("next_open_date") or "-"
            npdf = len(result.get("prospectus_pdfs", []))
            print(
                f"  [{done:4d}/{total}] {code:<20}"
                f"  成立:{est}  到期:{mat}  开放:{opn}  PDF:{npdf}"
            )

    # 3. 合并旧记录（防止因网络抖动导致的字段丢失）
    MERGE_FIELDS = [
        "establishment_date", "maturity_date", "subscription_period",
        "min_purchase_amount", "term", "min_hold_period",
        "currency", "currency_source", "detail_url",
    ]
    if OUTPUT_PATH.exists():
        try:
            with open(OUTPUT_PATH, "r", encoding="utf-8") as f:
                old_data = json.load(f)
            old_index = {p["product_code"]: p for p in old_data.get("products", []) if p.get("product_code")}
            merged = 0
            for r in results:
                old = old_index.get(r.get("product_code", ""))
                if old:
                    for field in MERGE_FIELDS:
                        if r.get(field) is None and old.get(field) is not None:
                            r[field] = old[field]
                            merged += 1
                    # PDF 链接：保留旧的（如果新的为空）
                    if not r.get("prospectus_pdfs") and old.get("prospectus_pdfs"):
                        r["prospectus_pdfs"] = old["prospectus_pdfs"]
            if merged:
                print(f"[BOC] 已从旧记录回填 {merged} 个空字段")
        except Exception as e:
            print(f"[BOC] 无法读取旧记录用于合并: {e}")

    # 4. 按产品代码排序后保存
    results.sort(key=lambda x: x.get("product_code", ""))
    output = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "total": len(results),
        "products": results,
    }
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\n[BOC] 元数据已保存 -> {OUTPUT_PATH}  ({len(results)} 条)")


    # 简单统计
    has_est = sum(1 for r in results if r.get("establishment_date"))
    has_mat = sum(1 for r in results if r.get("maturity_date"))
    has_opn = sum(1 for r in results if r.get("next_open_date"))
    has_pdf = sum(1 for r in results if r.get("prospectus_pdfs"))
    has_cur = sum(1 for r in results if r.get("currency"))
    print(f"     成立日:   {has_est}/{len(results)}")
    print(f"     到期日:   {has_mat}/{len(results)}")
    print(f"     开放日:   {has_opn}/{len(results)}")
    print(f"     PDF链接:  {has_pdf}/{len(results)}")
    print(f"     货币单位: {has_cur}/{len(results)}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="抓取中银理财产品元数据")
    parser.add_argument("--max", type=int, default=None,
                        help="仅处理前 N 个产品（调试用）")
    args = parser.parse_args()
    asyncio.run(main(max_products=args.max))

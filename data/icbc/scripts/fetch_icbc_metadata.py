"""
data/icbc/scripts/fetch_icbc_metadata.py

为工商银行（ICBC）理财产品拉取/抓取元数据：
  - 成立日 (establishment_date)
  - 到期日 (maturity_date)
  - 起购金额 + 货币单位 (min_purchase_amount / currency)
  - 风险等级 (risk_level)

流程：
  1. 读取 config/icbc_products.yaml 里的目标代码。
  2. 遍历 servlet 列表页进行活跃理财代码及风险等级的在线发现。
  3. 对于发现的代码，调用 getNetValueList API 抓取其最新的名称与封闭日期信息，解析出成立日与到期日。
  4. 对于未从列表页发现的目标代码，尝试结合 data/icbc/currencies.json 的静态名称/币种，再通过 API 补全日期。
  5. 合并并保存到 data/icbc/product_metadata.json。
"""

import asyncio
import json
import re
import sys
import argparse
import ssl
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any

import httpx
import yaml

# Windows GBK 终端下强制 UTF-8 输出
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

# ──────────────────────────────────────────────
# 常量
# ──────────────────────────────────────────────
DISCOVERY_URL = "https://mybank.icbc.com.cn/servlet/ICBCBaseReqServletNoSession"
NET_VALUE_URL = "https://papi.icbc.com.cn/finance/deposit/consignment/getNetValueList"
OUTPUT_PATH = Path("data/icbc/product_metadata.json")
CURRENCIES_JSON_PATH = Path("data/icbc/currencies.json")
PRODUCTS_YAML_PATH = Path("config/icbc_products.yaml")

CONCURRENCY = 5  # 并发控制，限制为5

# User Agent
DISCOVERY_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; WOW64; Trident/7.0; rv:11.0) like Gecko",
    "Content-Type": "application/x-www-form-urlencoded"
}

NET_VALUE_HEADERS = {
    "Content-Type": "application/json",
    "Origin": "https://www.icbc.com.cn",
    "Referer": "https://www.icbc.com.cn/"
}

# 货币映射
CURRENCY_MAP = {
    "美元": "USD",
    "USD": "USD",
    "港币": "HKD",
    "港元": "HKD",
    "HKD": "HKD",
    "欧元": "EUR",
    "EUR": "EUR",
    "英镑": "GBP",
    "GBP": "GBP",
    "日元": "JPY",
    "JPY": "JPY",
    "澳元": "AUD",
    "澳大利亚元": "AUD",
    "元": "CNY",
    "人民币": "CNY",
}

# ──────────────────────────────────────────────
# 辅助解析器
# ──────────────────────────────────────────────
def parse_icbc_dates(name: str) -> (Optional[str], Optional[str]):
    """从产品名中解析封闭期成立日与到期日"""
    # 匹配 2023.4.19-2023.10.24 或 2023/04/19-2023/10/24
    pattern = r"(\d{4})[\./](\d{1,2})[\./](\d{1,2})\s*-\s*(\d{4})[\./](\d{1,2})[\./](\d{1,2})"
    m = re.search(pattern, name)
    if m:
        try:
            est = f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
            mat = f"{m.group(4)}-{int(m.group(5)):02d}-{int(m.group(6)):02d}"
            return est, mat
        except ValueError:
            pass
            
    # 单独匹配成立日
    pattern_est = r"(?:成立|起息|开始)\s*(\d{4})[\./](\d{1,2})[\./](\d{1,2})"
    m_est = re.search(pattern_est, name)
    est = None
    if m_est:
        try:
            est = f"{m_est.group(1)}-{int(m_est.group(2)):02d}-{int(m_est.group(3)):02d}"
        except ValueError:
            pass
            
    # 单独匹配到期日
    pattern_mat = r"(?:到期|结束)\s*(\d{4})[\./](\d{1,2})[\./](\d{1,2})"
    m_mat = re.search(pattern_mat, name)
    mat = None
    if m_mat:
        try:
            mat = f"{m_mat.group(1)}-{int(m_mat.group(2)):02d}-{int(m_mat.group(3)):02d}"
        except ValueError:
            pass
            
    return est, mat

def infer_currency_from_name(name: str) -> str:
    """根据名字推断货币"""
    for zh, iso in CURRENCY_MAP.items():
        if zh in name:
            return iso
    return "CNY"

def map_icbc_risk(raw_risk: str) -> str:
    """将工行 PR1-PR5 风险等级转换为 R1-R5 格式"""
    if not raw_risk:
        return "R2中低风险"  # 默认兜底
    if "PR1" in raw_risk or "R1" in raw_risk:
        return "R1低风险"
    if "PR2" in raw_risk or "R2" in raw_risk:
        return "R2中低风险"
    if "PR3" in raw_risk or "R3" in raw_risk:
        return "R3中等风险"
    if "PR4" in raw_risk or "R4" in raw_risk:
        return "R4中高风险"
    if "PR5" in raw_risk or "R5" in raw_risk:
        return "R5高风险"
    return raw_risk

# ──────────────────────────────────────────────
# 1. 在线发现活跃产品代码与基础信息
# ──────────────────────────────────────────────
def parse_chunks(html: str) -> List[Dict[str, Any]]:
    chunks = html.split('ebdp-pc4promote-circularcontainer-wrapper')
    results = []
    for chunk in chunks[1:]:
        idx_match = re.search(r'id=["\']circularcontainer_(\d+)["\']', chunk)
        if not idx_match:
            idx_match = re.search(r'id=["\']circularcontainer_(\d+)-wrapper["\']', chunk)
        if not idx_match:
            continue
            
        # 提取 setTitle, setFloatMsg, buySubmit
        title_match = re.search(r'setTitle\(\"([^\"]+)\"\)', chunk)
        if not title_match:
            title_match = re.search(r"setTitle\('([^']+)'\)", chunk)
            
        risk_match = re.search(r'setFloatMsg\(\"([^\"]+)\"\)', chunk)
        if not risk_match:
            risk_match = re.search(r"setFloatMsg\('([^']+)'\)", chunk)
            
        code_match = re.search(r"buySubmit\('([^']+)'", chunk)
        
        # 起购金额
        min_purchase = None
        # sdoublelabel2_{idx}-content contains 起购金额
        p_match = re.search(r'sdoublelabel2_\d+-content"><b>([\d,]+)</b>(.*?)</div', chunk)
        if p_match:
            min_purchase = p_match.group(1).replace(",", "")
            
        # 期限
        term = None
        # sdoublelabel3_{idx}-content contains 期限
        t_match = re.search(r'sdoublelabel3_\d+-content">(.*?)</div', chunk)
        if t_match:
            term = re.sub(r'<[^>]+>', '', t_match.group(1)).strip()
            
        title = title_match.group(1) if title_match else None
        risk = risk_match.group(1) if risk_match else None
        code = code_match.group(1) if code_match else None
        
        if code:
            results.append({
                "product_code": code,
                "product_name": title,
                "risk_level": map_icbc_risk(risk) if risk else None,
                "min_purchase_amount": min_purchase,
                "term": term
            })
    return results

async def discover_active_products(client: httpx.AsyncClient) -> Dict[str, Dict[str, Any]]:
    print("[ICBC] 正在遍历发现工行在线活跃理财产品...")
    discovered = {}
    page = 1
    max_pages = 25  # 安全限制，防止死循环
    
    while page <= max_pages:
        page_flag = "0" if page == 1 else "2"
        condition = f"$$$$$$$${page_flag}${page}$$1"
        
        payload = {
            "dse_operationName": "per_FinanceCurProListP3NSOp",
            "nowPageNum_turn": str(page),
            "pageFlag_turn": page_flag,
            "Area_code": "0200",
            "useFinanceSolrFlag": "1",
            "financeQueryCondition": condition
        }
        
        try:
            resp = await client.post(DISCOVERY_URL, headers=DISCOVERY_HEADERS, data=payload, timeout=20)
            if resp.status_code != 200:
                print(f"  [ICBC] 发现列表在第 {page} 页失败: 状态码 {resp.status_code}")
                break
                
            html = resp.content.decode("gb18030", errors="ignore")
            parsed_list = parse_chunks(html)
            if not parsed_list:
                print(f"  [ICBC] 第 {page} 页未解析出产品。停止。")
                break
                
            # 检查是否全部重复
            new_found = 0
            for item in parsed_list:
                code = item["product_code"]
                if code not in discovered:
                    discovered[code] = item
                    new_found += 1
                    
            print(f"  [ICBC] 列表第 {page} 页: 发现 {len(parsed_list)} 个产品 (新增 {new_found} 个)")
            if new_found == 0:
                print(f"  [ICBC] 第 {page} 页无新增产品，结束发现。")
                break
                
            page += 1
            await asyncio.sleep(0.5)
        except Exception as e:
            print(f"  [ICBC] 第 {page} 页发现异常: {repr(e)}")
            break
            
    print(f"[ICBC] 在线活跃理财产品发现完成，共发现 {len(discovered)} 个产品")
    return discovered

# ──────────────────────────────────────────────
# 2. 从 getNetValueList API 补全详细动态元数据
# ──────────────────────────────────────────────
async def fetch_product_net_value_details(
    client: httpx.AsyncClient,
    code: str,
    semaphore: asyncio.Semaphore
) -> Optional[Dict[str, Any]]:
    payload = {
        "prodId": code,
        "pageIndex": 1,
        "pageSize": 5
    }
    
    async with semaphore:
        for attempt in range(2):
            try:
                resp = await client.post(NET_VALUE_URL, headers=NET_VALUE_HEADERS, json=payload, timeout=15)
                if resp.status_code == 200:
                    content = resp.content.decode("gb18030", errors="ignore")
                    data = json.loads(content)
                    records = data.get("data", {}).get("list", [])
                    if records:
                        first = records[0]
                        prod_name = first.get("prodName", "")
                        
                        # 解析日期
                        est, mat = parse_icbc_dates(prod_name)
                        
                        # 解析币种
                        currency = infer_currency_from_name(prod_name)
                        
                        return {
                            "product_name_detailed": prod_name,
                            "establishment_date": est,
                            "maturity_date": mat,
                            "currency": currency,
                            "fSubscribePrice": first.get("fSubscribePrice")
                        }
                    else:
                        # 成功返回但列表为空
                        return {}
                await asyncio.sleep(0.2)
            except Exception as e:
                if attempt == 1:
                    print(f"  [ICBC] 获取 {code} 净值数据失败: {repr(e)}")
        return None

# ──────────────────────────────────────────────
# 主流程
# ──────────────────────────────────────────────
async def main(max_products: Optional[int] = None):
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    
    # ── A. 载入种子与静态辅助配置 ──
    target_symbols = set()
    if PRODUCTS_YAML_PATH.exists():
        try:
            with open(PRODUCTS_YAML_PATH, "r", encoding="utf-8") as f:
                config = yaml.safe_load(f)
            symbols = config.get("symbols", [])
            target_symbols.update(symbols)
            print(f"[ICBC] 从 {PRODUCTS_YAML_PATH} 载入种子代码 {len(symbols)} 个: {symbols}")
        except Exception as e:
            print(f"[ICBC] 读取 {PRODUCTS_YAML_PATH} 失败: {e}")
            
    static_currencies = {}
    if CURRENCIES_JSON_PATH.exists():
        try:
            with open(CURRENCIES_JSON_PATH, "r", encoding="utf-8") as f:
                static_currencies = json.load(f)
            print(f"[ICBC] 从 {CURRENCIES_JSON_PATH} 载入静态币种映射 {len(static_currencies)} 个")
        except Exception as e:
            print(f"[ICBC] 读取 {CURRENCIES_JSON_PATH} 失败: {e}")
            
    # SSL 配置
    ssl_context = ssl.create_default_context()
    ssl_context.options |= 0x4  # OP_LEGACY_SERVER_CONNECT
    ssl_context.check_hostname = False
    ssl_context.verify_mode = ssl.CERT_NONE
    
    # ── B. 启动 API 客户端 ──
    async with httpx.AsyncClient(verify=ssl_context, trust_env=False) as client:
        # 1. 发现活跃理财产品
        discovered_products = await discover_active_products(client)
        
        # 2. 合并所有需获取详情的理财代码
        all_codes = set(discovered_products.keys()) | target_symbols
        all_codes = sorted(list(all_codes))
        
        if max_products:
            all_codes = all_codes[:max_products]
            print(f"[ICBC] 限制只处理前 {max_products} 个产品（调试模式）")
            
        print(f"[ICBC] 即将对 {len(all_codes)} 个理财产品执行动态字段查询...")
        
        # 3. 并发获取详细要素
        semaphore = asyncio.Semaphore(CONCURRENCY)
        tasks = {code: fetch_product_net_value_details(client, code, semaphore) for code in all_codes}
        
        results = []
        done = 0
        total = len(tasks)
        
        for code in all_codes:
            detail = await tasks[code]
            done += 1
            
            # 基础元素（来自列表页发现，或从静态库/种子补全）
            disc = discovered_products.get(code, {})
            name = disc.get("product_name")
            risk = disc.get("risk_level") or "R2中低风险"
            min_purchase = disc.get("min_purchase_amount")
            term = disc.get("term")
            
            # 如果列表没发现，尝试用静态辅助库补全名字与起购金额
            if not name and code in static_currencies:
                name = static_currencies[code].get("name")
                
            currency = "CNY"
            est_date = None
            mat_date = None
            currency_source = "default"
            
            if detail:
                # 动态查询获取的信息
                detail_name = detail.get("product_name_detailed")
                if detail_name:
                    name = detail_name
                est_date = detail.get("establishment_date")
                mat_date = detail.get("maturity_date")
                currency = detail.get("currency", "CNY")
                currency_source = "api_inferred" if detail.get("currency") else "default"
                
                # 动态起购价格兜底
                if not min_purchase and detail.get("fSubscribePrice"):
                    min_purchase = str(detail["fSubscribePrice"])
                    
            # 进一步尝试从静态库补全货币
            if currency == "CNY" and code in static_currencies:
                static_cur = static_currencies[code].get("currency", "元")
                currency = CURRENCY_MAP.get(static_cur, "CNY")
                currency_source = "static_mapping"
                
            # 从名字进一步推断货币
            if currency == "CNY" and name:
                currency = infer_currency_from_name(name)
                currency_source = "name_inference"
                
            meta = {
                "product_code": code,
                "product_name": name or f"工银理财{code}",
                "risk_level": risk,
                "detail_url": None,
                "establishment_date": est_date,
                "maturity_date": mat_date,
                "subscription_period": None,
                "min_purchase_amount": min_purchase,
                "currency": currency,
                "next_open_date": None,
                "term": term,
                "prospectus_pdfs": [],
                "fetched_at": datetime.now().isoformat(timespec="seconds"),
                "currency_source": currency_source,
            }
            results.append(meta)
            
            print(
                f"  [{done:4d}/{total}] {code:<20}"
                f"  币种:{currency:<4}  成立:{est_date or '-'}  到期:{mat_date or '-'}  风险:{risk}"
            )
            
    # ── C. 合并旧记录（保留以前抓取的数据，防止有字段本次抖动丢失） ──
    if OUTPUT_PATH.exists():
        try:
            with open(OUTPUT_PATH, "r", encoding="utf-8") as f:
                old_data = json.load(f)
            old_index = {p["product_code"]: p for p in old_data.get("products", []) if p.get("product_code")}
            merged = 0
            for r in results:
                old = old_index.get(r["product_code"])
                if old:
                    for field in ["establishment_date", "maturity_date", "min_purchase_amount", "currency", "risk_level", "term"]:
                        if r.get(field) is None and old.get(field) is not None:
                            r[field] = old[field]
                            merged += 1
            if merged:
                print(f"[ICBC] 已从旧记录回填 {merged} 个空字段")
        except Exception as e:
            print(f"[ICBC] 无法读取旧记录进行合并: {e}")
            
    # ── D. 保存结果 ──
    results.sort(key=lambda x: x.get("product_code", ""))
    output = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "total": len(results),
        "products": results,
    }
    
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
        
    print(f"\n[ICBC] 元数据已保存 -> {OUTPUT_PATH}  ({len(results)} 条)")
    
    # 简单统计
    has_est = sum(1 for r in results if r.get("establishment_date"))
    has_mat = sum(1 for r in results if r.get("maturity_date"))
    has_cur = sum(1 for r in results if r.get("currency"))
    has_rsk = sum(1 for r in results if r.get("risk_level"))
    print(f"     成立日:   {has_est}/{len(results)}")
    print(f"     到期日:   {has_mat}/{len(results)}")
    print(f"     风险等级: {has_rsk}/{len(results)}")
    print(f"     货币单位: {has_cur}/{len(results)}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="获取工商银行理财产品元数据")
    parser.add_argument("--max", type=int, default=None, help="仅处理前 N 个产品（调试用）")
    args = parser.parse_args()
    asyncio.run(main(max_products=args.max))

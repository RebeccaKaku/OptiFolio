"""
data/bosc/scripts/fetch_bosc_metadata.py

为上海银行（BOSC）理财产品提取/抓取元数据：
  - 成立日 (establishment_date)
  - 到期日 (maturity_date)
  - 起购金额 + 货币单位 (min_purchase_amount / currency)
  - 下一开放申赎日 (next_open_date)
  - 风险等级 (risk_level)
  - 期限/周期 (term)

主要从本地最新的 `data/bosc/raw/bosc_all_products_snapshot_*.json` 提取，并包含可选的在线 API 抓取作为回退/更新。
输出：data/bosc/product_metadata.json
用法：python data/bosc/scripts/fetch_bosc_metadata.py [--max N]
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

# Windows GBK 终端下强制 UTF-8 输出
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

# ──────────────────────────────────────────────
# 常量
# ──────────────────────────────────────────────
PRODUCT_LIST_URL = "https://www.bosc.cn/apiQry/apiPCQry/qryPcFinanceProductZh"
OUTPUT_PATH = Path("data/bosc/product_metadata.json")
SNAPSHOT_DIR = Path("data/bosc/raw")

HEADERS = {
    "Content-Type": "application/json",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
}

RISK_LEVEL_MAP = {
    "1": "R1极低风险",
    "2": "R2中低风险",
    "3": "R3中等风险",
    "4": "R4中高风险",
    "5": "R5高风险",
}

# ──────────────────────────────────────────────
# 从本地最新的 Snapshot 文件中读取数据
# ──────────────────────────────────────────────
def load_latest_snapshot() -> List[Dict[str, Any]]:
    if not SNAPSHOT_DIR.exists():
        print(f"[BOSC] Snapshot 目录不存在: {SNAPSHOT_DIR}")
        return []
    
    # 查找所有 bosc_all_products_snapshot_*.json 并按字母（也是日期）排序
    files = sorted(SNAPSHOT_DIR.glob("bosc_all_products_snapshot_*.json"))
    if not files:
        print(f"[BOSC] 未在 {SNAPSHOT_DIR} 找到任何快照文件")
        return []
    
    latest_file = files[-1]
    print(f"[BOSC] 正在读取最新快照文件: {latest_file}")
    try:
        with open(latest_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        records = data.get("data", {}).get("records", [])
        print(f"[BOSC] 从快照成功加载 {len(records)} 个产品")
        return records
    except Exception as e:
        print(f"[BOSC] 读取快照失败: {e}")
        return []

# ──────────────────────────────────────────────
# 可选的在线 API 抓取（如果网络允许）
# ──────────────────────────────────────────────
async def fetch_product_rows_online() -> List[Dict[str, Any]]:
    print(f"[BOSC] 尝试在线拉取上海银行理财产品列表...")
    
    ssl_context = ssl.create_default_context()
    ssl_context.options |= 0x4  # OP_LEGACY_SERVER_CONNECT
    # 关闭证书校验以提高兼容性
    ssl_context.check_hostname = False
    ssl_context.verify_mode = ssl.CERT_NONE
    
    payload = {"current": 1, "size": 1000}
    
    # 我们测试有 proxy 和没有 proxy 的情况
    # 在有些环境里 trust_env=False 能够绕过引发 EOF 的代理；在有些环境里则相反。
    # 采用两段式抓取：先尝试 trust_env=False，如果超时/失败再尝试 trust_env=True。
    for trust_env_option in [False, True]:
        try:
            print(f"  [BOSC] 在线拉取尝试 (trust_env={trust_env_option})...")
            async with httpx.AsyncClient(verify=ssl_context, trust_env=trust_env_option) as client:
                resp = await client.post(PRODUCT_LIST_URL, headers=HEADERS, json=payload, timeout=10)
                if resp.status_code == 200:
                    data = resp.json()
                    records = data.get("data", {}).get("records", [])
                    print(f"  [BOSC] 在线拉取成功! 获取到 {len(records)} 个产品")
                    return records
                else:
                    print(f"  [BOSC] 在线拉取状态码异常: {resp.status_code}")
        except Exception as e:
            print(f"  [BOSC] 在线拉取失败 (trust_env={trust_env_option}): {repr(e)}")
            
    print("[BOSC] 在线拉取全部失败，将仅使用本地快照数据")
    return []

# ──────────────────────────────────────────────
# 解析并转换原始 product 记录
# ──────────────────────────────────────────────
def parse_product_record(row: Dict[str, Any]) -> Dict[str, Any]:
    code = row.get("prdCode", "")
    name = row.get("prdName", "")
    
    # 风险等级映射
    raw_risk = str(row.get("riskLevel", ""))
    risk_level = RISK_LEVEL_MAP.get(raw_risk, f"R{raw_risk}") if raw_risk else None
    
    # 起购金额
    min_purchase = row.get("pfirstAmt")
    if min_purchase is not None:
        min_purchase = str(min_purchase)
        
    # 期限周期
    term = row.get("periodDesc")
    if not term:
        cycle_days = row.get("cycleDays")
        if cycle_days and cycle_days != "0":
            term = f"{cycle_days}天"
            
    # 下一开放日
    next_open = row.get("nextClearDate") or row.get("currNetCycleConfirmDate")
    if next_open and next_open == "-":
        next_open = None
        
    # 成立日与到期日
    estab = row.get("estabDate") or row.get("incomeDate")
    maturity = row.get("incomeEndDate")
    
    return {
        "product_code": code,
        "product_name": name,
        "risk_level": risk_level,
        "detail_url": None,  # 上海银行无公开免密产品静态详情页
        "establishment_date": estab,
        "maturity_date": maturity,
        "subscription_period": None,
        "min_purchase_amount": min_purchase,
        "currency": row.get("currType") or "CNY",
        "next_open_date": next_open,
        "term": term or None,
        "prospectus_pdfs": [],
        "fetched_at": datetime.now().isoformat(timespec="seconds"),
        "currency_source": "api_field" if row.get("currType") else "default",
    }

# ──────────────────────────────────────────────
# 主流程
# ──────────────────────────────────────────────
async def main(max_products: Optional[int] = None):
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    
    # 1. 优先载入本地快照
    raw_records = load_latest_snapshot()
    
    # 2. 尝试在线获取更新
    online_records = await fetch_product_rows_online()
    
    # 3. 合并数据
    # 使用字典按产品代码去重，在线数据优先
    records_dict = {}
    for r in raw_records:
        if r.get("prdCode"):
            records_dict[r["prdCode"]] = r
            
    for r in online_records:
        if r.get("prdCode"):
            records_dict[r["prdCode"]] = r
            
    all_raw = list(records_dict.values())
    
    if max_products:
        all_raw = all_raw[:max_products]
        print(f"[BOSC] 限制只处理前 {max_products} 个产品（调试模式）")
        
    # 4. 解析字段
    results = []
    for row in all_raw:
        parsed = parse_product_record(row)
        results.append(parsed)
        
    # 5. 合并旧记录（防止有字段在本次更新中缺失）
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
                print(f"[BOSC] 已从旧记录回填 {merged} 个空字段")
        except Exception as e:
            print(f"[BOSC] 无法读取旧记录进行合并: {e}")
            
    # 6. 排序并保存
    results.sort(key=lambda x: x.get("product_code", ""))
    output = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "total": len(results),
        "products": results,
    }
    
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
        
    print(f"\n[BOSC] 元数据已保存 -> {OUTPUT_PATH}  ({len(results)} 条)")
    
    # 简单统计
    has_est = sum(1 for r in results if r.get("establishment_date"))
    has_mat = sum(1 for r in results if r.get("maturity_date"))
    has_opn = sum(1 for r in results if r.get("next_open_date"))
    has_cur = sum(1 for r in results if r.get("currency"))
    has_rsk = sum(1 for r in results if r.get("risk_level"))
    print(f"     成立日:   {has_est}/{len(results)}")
    print(f"     到期日:   {has_mat}/{len(results)}")
    print(f"     开放日:   {has_opn}/{len(results)}")
    print(f"     风险等级: {has_rsk}/{len(results)}")
    print(f"     货币单位: {has_cur}/{len(results)}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="获取上海银行理财产品元数据")
    parser.add_argument("--max", type=int, default=None, help="仅处理前 N 个产品（调试用）")
    args = parser.parse_args()
    asyncio.run(main(max_products=args.max))

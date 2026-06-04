"""BOC Structural Deposit fetcher — personal (GRSDRxxx) and institutional (CSDPYxxx).

Personal: https://www.boc.cn/sdbapp/pbsd4/ — bill page, server-rendered HTML
Institutional: https://www.bankofchina.com/cbservice/csdp/ — announcements + prospectuses

No JSON API exists for these products — data is scraped from HTML pages.
"""

import re
from typing import Dict, Any, Optional, List

import httpx
from bs4 import BeautifulSoup


class BocStructuredDepositFetcher:
    """Scrapes BOC structural deposit data from public HTML pages."""

    HEADERS = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

    # ── Personal structural deposits (个人结构性存款) ──────────────────

    async def fetch_personal_list(self) -> List[str]:
        """Get product codes from the personal structural deposit bill page."""
        print("    [BOC-SD] Fetching personal structural deposit list...")
        url = "https://www.boc.cn/sdbapp/pbsd4/"
        entries: List[Dict[str, str]] = []
        try:
            async with httpx.AsyncClient(follow_redirects=True, verify=False) as client:
                res = await client.get(url, headers=self.HEADERS, timeout=15)
                res.raise_for_status()
                soup = BeautifulSoup(res.text, "html.parser")
                for link in soup.find_all("a"):
                    text = link.text.strip()
                    href = link.get("href", "")
                    if re.match(r'^[A-Z0-9]{8,15}$', text) and text.isupper():
                        entries.append({"code": text, "href": href})
        except Exception as e:
            print(f"    [BOC-SD] Error: {e}")
        print(f"    [BOC-SD] Found {len(entries)} personal structural deposits.")
        return [e["code"] for e in entries]

    async def fetch_personal_detail(self, code: str) -> Optional[Dict[str, Any]]:
        """Scrape detail data for a single personal structural deposit."""
        print(f"    [BOC-SD] Detail for: {code}")
        try:
            async with httpx.AsyncClient(follow_redirects=True, verify=False) as client:
                # Find the detail URL from the list page
                res = await client.get("https://www.boc.cn/sdbapp/pbsd4/", headers=self.HEADERS, timeout=15)
                res.raise_for_status()
                soup = BeautifulSoup(res.text, "html.parser")
                detail_url = None
                for link in soup.find_all("a"):
                    if link.text.strip() == code and link.get("href"):
                        href = link["href"]
                        if href.startswith("./"):
                            detail_url = "https://www.boc.cn/sdbapp/pbsd4/" + href[2:]
                        elif href.startswith("/"):
                            detail_url = "https://www.boc.cn" + href
                        else:
                            detail_url = href.replace("boc.cn.", "boc.cn")
                        break
                if not detail_url:
                    return None
                res2 = await client.get(detail_url, headers=self.HEADERS, timeout=15)
                res2.raise_for_status()
                soup2 = BeautifulSoup(res2.text, "html.parser")
                text = soup2.get_text("\n", strip=True)
                return self._parse_detail(text, code)
        except Exception as e:
            print(f"    [BOC-SD] Error: {e}")
            return None

    # ── Institutional structural deposits (机构结构性存款) ──────────────

    async def fetch_institutional_list(self, max_pages: int = 5) -> List[Dict[str, str]]:
        """Get institutional structural deposits from the prospectus listing page.

        Scrapes https://www.bankofchina.com/cbservice/csdp/csdp3/ which has
        paginated listings (50 pages total). Each page has ~20 products.

        Args:
            max_pages: Maximum pages to scrape (default 5 = ~100 recent products).
        """
        print("    [BOC-SD] Fetching institutional structural deposit list...")
        results: List[Dict[str, str]] = []
        seen_codes: set = set()
        try:
            async with httpx.AsyncClient(follow_redirects=True, verify=False) as client:
                for page in range(1, max_pages + 1):
                    url = f"https://www.bankofchina.com/cbservice/csdp/csdp3/index_{page}.html" if page > 1 else "https://www.bankofchina.com/cbservice/csdp/csdp3/"
                    res = await client.get(url, headers=self.HEADERS, timeout=15)
                    if res.status_code != 200:
                        break
                    text = BeautifulSoup(res.text, "html.parser").get_text("\n", strip=True)
                    new_on_page = 0
                    for line in text.split('\n'):
                        line = line.strip()
                        m = re.match(
                            r'(CSDPY\d+)\s*'
                            r'(人民币|美元)\s*'
                            r'结构性存款\s*'
                            r'(\d{4})年(\d{1,2})月(\d{1,2})日起售\s*'
                            r'(\d+)天',
                            line
                        )
                        if m and m.group(1) not in seen_codes:
                            seen_codes.add(m.group(1))
                            results.append({
                                "code": m.group(1),
                                "currency": "CNY" if "人民币" in m.group(2) else "USD",
                                "name": f"{m.group(2)}结构性存款{m.group(1)}",
                                "start_date": f"{m.group(3)}-{m.group(4).zfill(2)}-{m.group(5).zfill(2)}",
                                "term_days": int(m.group(6)),
                            })
                            new_on_page += 1
                    if new_on_page == 0:
                        break
        except Exception as e:
            print(f"    [BOC-SD] Error: {e}")
        print(f"    [BOC-SD] Found {len(results)} institutional products (scanned {max_pages} pages).")
        return results

    # ── Shared parser ──────────────────────────────────────────────────

    def _parse_detail(self, text: str, code: str) -> Dict[str, Any]:
        """Parse vertical newline-separated BOC structural deposit detail page."""
        result: Dict[str, Any] = {"product_code": code, "source": "boc_structural_deposit_html"}
        currency_map = {"人民币": "CNY", "美元": "USD", "欧元": "EUR", "港币": "HKD", "英镑": "GBP", "日元": "JPY", "澳元": "AUD"}

        lines = [l.strip() for l in text.split('\n') if l.strip()]

        for i, line in enumerate(lines):
            if line == code and i + 10 < len(lines):
                result["product_name"] = lines[i + 1]
                for j in range(i + 2, i + 6):
                    if lines[j] in currency_map:
                        result["currency"] = currency_map[lines[j]]
                        for k in range(j + 1, min(j + 3, len(lines))):
                            if re.match(r'^\d+$', lines[k]):
                                result["term_days"] = int(lines[k])
                                break
                        break
                for j in range(i + 2, i + 8):
                    if re.match(r'\d{4}/\d{2}/\d{2}至\d{4}/\d{2}/\d{2}', lines[j]):
                        result["period"] = lines[j]
                        break
                for j in range(i + 3, i + 10):
                    if re.match(r'\d+\.?\d*%至\d+\.?\d*%', lines[j]):
                        result["expected_yield_range"] = lines[j]
                        break

            if '区间累计' in line or ('区间' in line and len(line) > 5 and not re.match(r'\d', line)):
                result["yield_structure"] = line
                for j in range(max(0, i - 2), min(i + 3, len(lines))):
                    if re.match(r'^[A-Z]{3,6}(/[A-Z]{3,6})?$', lines[j]):
                        result["underlying"] = lines[j]
                        break

            if re.match(r'^\d+\.?\d*%$', line) and 'floor_yield' not in result:
                result["floor_yield"] = line

            if line in ('个人', '机构', '个人/机构'):
                result["investor_type"] = line

            if re.match(r'^\d{4}/\d{2}/\d{2}$', line) and 'establishment_date' not in result:
                result["establishment_date"] = line.replace("/", "-")

            if re.match(r'\d{4}/\d{2}/\d{2}至\d{4}/\d{2}/\d{2}', line) and 'period' in result:
                result["observation_period"] = line

            if re.match(r'^\d+\.\d{4}$', line) and 'initial_price' not in result:
                result["initial_price"] = float(line)

            if re.match(r'^\d+\.?\d*/\d+\.?\d*$', line):
                result["observation_level"] = line

            if re.match(r'^[\d,]+\.\d{2}$', line):
                val = float(line.replace(",", ""))
                if 'issue_size' not in result:
                    result["issue_size"] = val
                elif 'derivative_investment' not in result:
                    result["derivative_investment"] = val
                elif 'derivative_fair_value' not in result:
                    result["derivative_fair_value"] = val

            m = re.search(r'账单日[：:]\s*(\d{4}-\d{2}-\d{2})', line)
            if m:
                result["bill_date"] = m.group(1)

            if re.match(r'^\d+\.?\d*%$', line) and 'bill_date' in result and 'floor_yield' in result:
                result["bill_date_yield"] = line

        return result

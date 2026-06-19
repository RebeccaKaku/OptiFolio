"""AI-based structured data extraction from unstructured text.

Uses DeepSeek API to parse PDF text into structured fee/constraint data.
Single responsibility: take text, return structured dict.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

_log = logging.getLogger(__name__)

import httpx


@dataclass
class BocProductFees:
    """Structured fee and constraint data extracted from BOC product PDF."""

    product_code: str = ""

    # Annual fees (decimal, e.g. 0.003 = 0.30%)
    management_fee: Optional[float] = None       # 固定管理费
    custody_fee: Optional[float] = None           # 托管费
    sales_service_fee: Optional[float] = None     # 销售服务费

    # One-time fees (decimal)
    subscription_fee: Optional[float] = None      # 认购费
    purchase_fee: Optional[float] = None          # 申购费
    redemption_fee: Optional[float] = None        # 赎回费

    # Performance fee
    has_performance_fee: bool = False             # 是否有超额业绩报酬
    performance_fee_rate: Optional[float] = None  # 超额业绩提成比例
    performance_fee_hurdle: Optional[str] = None  # 业绩基准/门槛描述

    # Sales restrictions
    sales_region: Optional[str] = None            # 销售区域
    sales_target: Optional[str] = None            # 销售对象
    min_purchase_amount: Optional[str] = None     # 起购金额

    # Metadata
    extraction_source: str = ""                   # "ai" or "regex"
    extraction_confidence: float = 0.0
    raw_text_snippet: str = ""                    # The text block used for extraction

    def to_dict(self) -> Dict[str, Any]:
        return {
            "product_code": self.product_code,
            "management_fee": self.management_fee,
            "custody_fee": self.custody_fee,
            "sales_service_fee": self.sales_service_fee,
            "subscription_fee": self.subscription_fee,
            "purchase_fee": self.purchase_fee,
            "redemption_fee": self.redemption_fee,
            "has_performance_fee": self.has_performance_fee,
            "performance_fee_rate": self.performance_fee_rate,
            "performance_fee_hurdle": self.performance_fee_hurdle,
            "sales_region": self.sales_region,
            "sales_target": self.sales_target,
            "min_purchase_amount": self.min_purchase_amount,
            "extraction_source": self.extraction_source,
            "extraction_confidence": self.extraction_confidence,
        }


EXTRACTION_PROMPT = """你是一个金融文档解析专家。请从以下银行理财产品说明书的文本中提取关键信息。

提取规则：
1. 所有费率以小数形式返回（如 0.30% 返回 0.003，不是 0.30）
2. 如果某个费用明确标注为"不收取"或"0"，返回 0.0
3. 如果文本中找不到某个字段，返回 null
4. 年化费率注意区分：文本中可能写成"0.30%"或"0.30％"或"0.30%（年化）"

请返回纯 JSON（不要 markdown 代码块），格式如下：
{
  "management_fee": 数字或null,
  "custody_fee": 数字或null,
  "sales_service_fee": 数字或null,
  "subscription_fee": 数字或null,
  "purchase_fee": 数字或null,
  "redemption_fee": 数字或null,
  "has_performance_fee": true或false,
  "performance_fee_rate": 数字或null,
  "performance_fee_hurdle": "文字描述或null",
  "sales_region": "文字或null",
  "sales_target": "文字或null",
  "min_purchase_amount": "文字或null",
  "notes": "任何额外的重要费用说明或null"
}

文本内容：
---
{text}
---"""


class DeepSeekExtractor:
    """Extract structured fee data from PDF text using DeepSeek API.

    Usage::

        extractor = DeepSeekExtractor(api_key="sk-...")
        fees = extractor.extract_fees(pdf_text, product_code="00QQ2YA")
        print(fees.management_fee)  # 0.003
    """

    BASE_URL = "https://api.deepseek.com/v1/chat/completions"
    MODEL = "deepseek-chat"

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.environ.get("DEEPSEEK_API_KEY", "")
        if not self.api_key:
            raise ValueError(
                "DEEPSEEK_API_KEY is required. Set it via env var or pass to constructor."
            )

    def extract_fees(
        self,
        pdf_text: str,
        product_code: str = "",
        max_input_chars: int = 6000,
    ) -> BocProductFees:
        """Extract fee data from PDF text.

        Args:
            pdf_text: Full text extracted from the PDF.
            product_code: BOC product code for identification.
            max_input_chars: Truncate input to this many characters to control cost.
        """
        # Truncate to control token usage
        text_snippet = pdf_text[:max_input_chars]

        prompt = EXTRACTION_PROMPT.format(text=text_snippet)

        result = self._call_api(prompt)
        return self._parse_result(result, product_code, text_snippet[:500])

    def _call_api(self, prompt: str, temperature: float = 0.0) -> Dict[str, Any]:
        """Call DeepSeek chat completions API."""
        payload = {
            "model": self.MODEL,
            "messages": [
                {"role": "system", "content": "你是一个精确的金融数据提取器。只返回JSON，不要任何解释。"},
                {"role": "user", "content": prompt},
            ],
            "temperature": temperature,
            "max_tokens": 800,
            "stream": False,
        }

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        resp = httpx.post(
            self.BASE_URL,
            json=payload,
            headers=headers,
            timeout=60,
        )
        resp.raise_for_status()
        data = resp.json()
        return json.loads(data["choices"][0]["message"]["content"])

    def _parse_result(
        self, raw: Dict[str, Any], product_code: str, snippet: str
    ) -> BocProductFees:
        """Parse the AI response into a BocProductFees dataclass."""
        return BocProductFees(
            product_code=product_code,
            management_fee=raw.get("management_fee"),
            custody_fee=raw.get("custody_fee"),
            sales_service_fee=raw.get("sales_service_fee"),
            subscription_fee=raw.get("subscription_fee"),
            purchase_fee=raw.get("purchase_fee"),
            redemption_fee=raw.get("redemption_fee"),
            has_performance_fee=bool(raw.get("has_performance_fee", False)),
            performance_fee_rate=raw.get("performance_fee_rate"),
            performance_fee_hurdle=raw.get("performance_fee_hurdle"),
            sales_region=raw.get("sales_region"),
            sales_target=raw.get("sales_target"),
            min_purchase_amount=raw.get("min_purchase_amount"),
            extraction_source="ai-deepseek",
            extraction_confidence=0.9,
            raw_text_snippet=snippet,
        )


class RegexFeeExtractor:
    """Fallback: regex-based fee extraction for well-structured PDFs.

    Much faster and cheaper than AI. Used when the PDF follows
    the standard BOC fee table format.
    """

    import re as _re

    # Pattern: 费用名称：【0.30】%（年化）or 费用名称：0.30%（年化）
    # BOC PDFs use 【】 brackets around the number
    FEE_PATTERN = _re.compile(
        r"(固定管理费|管理费|销售服务费|销售费|托管费|认购费|申购费|赎回费)"
        r"[：:\s]*"
        r"(?:【\s*)?"
        r"(\d+\.?\d*)"
        r"(?:\s*】)?"
        r"\s*[％%]"
    )

    # Pattern: detect performance fee presence and rate
    # "不收取超额业绩报酬" → no fee; "超额业绩报酬：X.XX％" → has fee
    PERFORMANCE_NO_FEE = _re.compile(
        r"(?:不收取|无|免收|无计提).{0,10}(?:超额业绩报酬?|业绩报酬?)"
    )
    PERFORMANCE_HAS_FEE = _re.compile(
        r"(?:超额业绩报酬?|业绩报酬?)[^。]{0,30}?(\d+\.?\d*)\s*[％%]"
    )

    def extract(self, text: str, product_code: str = "") -> BocProductFees:
        """Regex-based extraction for standard BOC PDFs."""
        fees = BocProductFees(product_code=product_code, extraction_source="regex")

        for match in self.FEE_PATTERN.finditer(text):
            name = match.group(1)
            value_str = match.group(2)
            value = float(value_str) / 100.0  # Convert X.XX% → 0.0XXX

            if "管理费" in name or "固定管理费" in name:
                if fees.management_fee is None:
                    fees.management_fee = value
            elif "托管费" in name:
                if fees.custody_fee is None:
                    fees.custody_fee = value
            elif "销售" in name:
                if fees.sales_service_fee is None:
                    fees.sales_service_fee = value
            elif "认购费" in name:
                fees.subscription_fee = value
            elif "申购费" in name:
                fees.purchase_fee = value
            elif "赎回费" in name:
                fees.redemption_fee = value

        # Check for performance fee
        if not self.PERFORMANCE_NO_FEE.search(text):
            pf_match = self.PERFORMANCE_HAS_FEE.search(text)
            if pf_match:
                fees.has_performance_fee = True
                try:
                    fees.performance_fee_rate = float(pf_match.group(1)) / 100.0
                except (ValueError, IndexError):
                    pass

        return fees

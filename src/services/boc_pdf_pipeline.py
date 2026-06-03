"""BOC PDF extraction pipeline — orchestrator.

Downloads product PDFs, extracts text, and parses fee/constraint data.
Uses regex as primary extractor (fast, cheap, handles standard BOC format).
AI extraction (DeepSeek) as fallback for complex/irregular PDFs.

Architecture:
    PdfExtractor → BocPdfPipeline.select_and_download()
                 → RegexFeeExtractor (primary, ~0 cost)
                 → DeepSeekExtractor (fallback, ~$0.001/PDF)

Usage::

    pipeline = BocPdfPipeline()
    results = pipeline.process_products(["AMHQLXTTUSD01B"])
    for r in results:
        print(r.to_dict())
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx

from src.core.paths import PROJECT_ROOT
from src.services.ai_extractor import (
    BocProductFees,
    DeepSeekExtractor,
    RegexFeeExtractor,
)
from src.services.pdf_parser import PdfContent, PdfExtractor


@dataclass
class PipelineResult:
    """Result of processing one product PDF."""

    product_code: str
    success: bool
    fees: Optional[BocProductFees] = None
    error: str = ""
    extractor_used: str = ""  # "regex" or "ai"
    elapsed_seconds: float = 0.0


class BocPdfPipeline:
    """End-to-end pipeline: download → extract → parse → store."""

    def __init__(
        self,
        metadata_path: Optional[Path] = None,
        output_path: Optional[Path] = None,
        deepseek_api_key: Optional[str] = None,
    ):
        self.metadata_path = metadata_path or PROJECT_ROOT / "config" / "boc_product_metadata.json"
        self.output_path = output_path or PROJECT_ROOT / "config" / "boc_product_fees.json"
        self.pdf_extractor = PdfExtractor()
        self.regex_extractor = RegexFeeExtractor()
        self.ai_extractor: Optional[DeepSeekExtractor] = None
        if deepseek_api_key:
            try:
                self.ai_extractor = DeepSeekExtractor(api_key=deepseek_api_key)
            except ValueError:
                pass

        self._metadata: Optional[Dict[str, Any]] = None

    # ── public API ─────────────────────────────────────────────────────

    def load_metadata(self) -> Dict[str, Any]:
        """Load the BOC product metadata index."""
        if self._metadata is not None:
            return self._metadata
        with open(self.metadata_path, encoding="utf-8") as f:
            self._metadata = json.load(f)
        return self._metadata

    def get_product_pdf_urls(self, product_code: str) -> List[str]:
        """Get prospectus PDF URLs for a product."""
        meta = self.load_metadata()
        for p in meta.get("products", []):
            if p.get("product_code") == product_code:
                pdfs = p.get("prospectus_pdfs", [])
                return [pdf["url"] for pdf in pdfs]
        return []

    def process_products(
        self,
        product_codes: List[str],
        use_ai_fallback: bool = True,
        max_pdfs_per_product: int = 1,
    ) -> List[PipelineResult]:
        """Process multiple products — download + extract fees.

        Args:
            product_codes: BOC product codes to process.
            use_ai_fallback: If True, fall back to DeepSeek when regex fails.
            max_pdfs_per_product: Max PDFs to download per product (1=latest only).

        Returns:
            One PipelineResult per product.
        """
        results: List[PipelineResult] = []
        for code in product_codes:
            t0 = time.time()
            try:
                result = self._process_one(code, use_ai_fallback, max_pdfs_per_product)
            except Exception as exc:
                result = PipelineResult(
                    product_code=code,
                    success=False,
                    error=f"{type(exc).__name__}: {exc}",
                    elapsed_seconds=time.time() - t0,
                )
            results.append(result)
        return results

    def process_portfolio(self, use_ai_fallback: bool = False) -> List[PipelineResult]:
        """Process BOC products in the current portfolio."""
        codes = self._get_portfolio_boc_codes()
        if not codes:
            print("No BOC products found in portfolio.")
            return []
        print(f"Processing {len(codes)} BOC products from portfolio: {codes}")
        return self.process_products(codes, use_ai_fallback=use_ai_fallback)

    def save_results(self, results: List[PipelineResult]) -> Path:
        """Save extraction results to JSON."""
        existing: Dict[str, Any] = {}
        if self.output_path.exists():
            with open(self.output_path, encoding="utf-8") as f:
                existing = json.load(f)

        records = existing.get("products", [])
        existing_codes = {r.get("product_code") for r in records}

        for r in results:
            if r.success and r.fees:
                if r.fees.product_code in existing_codes:
                    # Update existing
                    for i, rec in enumerate(records):
                        if rec.get("product_code") == r.fees.product_code:
                            records[i] = r.fees.to_dict()
                            break
                else:
                    records.append(r.fees.to_dict())

        output = {
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "total": len(records),
            "products": records,
        }

        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.output_path, "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2)

        return self.output_path

    # ── internal ───────────────────────────────────────────────────────

    def _process_one(
        self, code: str, use_ai: bool, max_pdfs: int,
    ) -> PipelineResult:
        t0 = time.time()
        urls = self.get_product_pdf_urls(code)

        if not urls:
            return PipelineResult(
                product_code=code, success=False,
                error="No PDF URLs found", elapsed_seconds=time.time() - t0,
            )

        # Download and extract text from first N PDFs
        best_fees: Optional[BocProductFees] = None
        extractor_used = ""

        for url in urls[:max_pdfs]:
            try:
                content = self.pdf_extractor.extract_from_url(url, timeout=30)
            except Exception as exc:
                continue  # Try next PDF

            # 1. Try regex first (fast, free)
            fees = self.regex_extractor.extract(content.raw_text, code)
            if self._is_meaningful(fees):
                best_fees = fees
                extractor_used = "regex"
                break

            # 2. AI fallback
            if use_ai and self.ai_extractor:
                try:
                    fees = self.ai_extractor.extract_fees(
                        content.raw_text, code,
                    )
                    if self._is_meaningful(fees):
                        best_fees = fees
                        extractor_used = "ai"
                        break
                except Exception:
                    pass

        if best_fees is None:
            return PipelineResult(
                product_code=code, success=False,
                error="Could not extract fees from any PDF",
                elapsed_seconds=time.time() - t0,
            )

        return PipelineResult(
            product_code=code, success=True, fees=best_fees,
            extractor_used=extractor_used,
            elapsed_seconds=time.time() - t0,
        )

    @staticmethod
    def _is_meaningful(fees: BocProductFees) -> bool:
        """Check if extraction produced useful data."""
        return any([
            fees.management_fee is not None,
            fees.custody_fee is not None,
            fees.sales_service_fee is not None,
            fees.subscription_fee is not None,
            fees.purchase_fee is not None,
            fees.redemption_fee is not None,
        ])

    @staticmethod
    def _get_portfolio_boc_codes() -> List[str]:
        """Find BOC product codes in portfolio YAML."""
        import yaml

        portfolio_path = PROJECT_ROOT / "local" / "portfolio.yaml"
        if not portfolio_path.exists():
            portfolio_path = PROJECT_ROOT / "config" / "portfolio.yaml"
        if not portfolio_path.exists():
            return []

        with open(portfolio_path, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}

        # BOC codes are alphanumeric like "AMHQLXTTUSD01B"
        codes: List[str] = []
        for symbol in data.get("positions", {}):
            # BOC product codes: all uppercase alphanumeric, typically 6-15 chars
            if symbol.isupper() and any(c.isdigit() for c in symbol):
                codes.append(symbol)
        return codes

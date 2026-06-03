#!/usr/bin/env python
"""Extract fee data from BOC wealth management product PDFs.

Downloads product prospectus PDFs, extracts fee/constraint data using
regex (primary) with optional AI fallback (DeepSeek).

Usage:
    # Process specific products
    python tools/extract_boc_pdf_fees.py --codes AMHQLXTTUSD01B,00QQ2YA

    # Process all BOC products in portfolio
    python tools/extract_boc_pdf_fees.py --portfolio

    # Process with AI fallback for irregular PDFs
    python tools/extract_boc_pdf_fees.py --portfolio --ai-fallback

    # Dry-run: show what would be processed without downloading
    python tools/extract_boc_pdf_fees.py --portfolio --dry-run

Output:
    Results saved to config/boc_product_fees.json
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.services.boc_pdf_pipeline import BocPdfPipeline


def main():
    parser = argparse.ArgumentParser(
        description="Extract fees from BOC product PDFs",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--codes", help="Comma-separated product codes")
    group.add_argument("--portfolio", action="store_true", help="Process portfolio BOC products")
    parser.add_argument("--ai-fallback", action="store_true", help="Use DeepSeek AI when regex fails")
    parser.add_argument("--max-pdfs", type=int, default=1, help="Max PDFs per product (default: 1)")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be processed, no downloads")
    args = parser.parse_args()

    pipeline = BocPdfPipeline()

    # Resolve product codes
    if args.codes:
        codes = [c.strip() for c in args.codes.split(",")]
    else:
        codes = pipeline._get_portfolio_boc_codes()

    if not codes:
        print("No BOC product codes found.")
        return

    if args.dry_run:
        print(f"Would process {len(codes)} products:")
        for code in codes:
            urls = pipeline.get_product_pdf_urls(code)
            print(f"  {code}: {len(urls)} PDF(s) available")
        return

    print(f"Processing {len(codes)} BOC products...")
    results = pipeline.process_products(
        codes,
        use_ai_fallback=args.ai_fallback,
        max_pdfs_per_product=args.max_pdfs,
    )

    # Report
    success = [r for r in results if r.success]
    failed = [r for r in results if not r.success]
    print(f"\nDone: {len(success)} success, {len(failed)} failed")

    if success:
        for r in success:
            f = r.fees
            print(f"  {r.product_code}: mgmt={f.management_fee}, custody={f.custody_fee}, "
                  f"sales={f.sales_service_fee}, perf={f.has_performance_fee} "
                  f"[{r.extractor_used}]")

    if failed:
        for r in failed:
            print(f"  {r.product_code}: FAILED — {r.error}")

    # Save
    output_path = pipeline.save_results(results)
    print(f"\nResults saved to: {output_path}")


if __name__ == "__main__":
    main()

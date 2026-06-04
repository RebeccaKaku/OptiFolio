#!/usr/bin/env python
"""Extract fee data from BOC wealth management product PDFs.

Usage:
    cd OptiFolio
    python data/boc/scripts/extract_fees.py --codes AMHQLXTTUSD01B
    python data/boc/scripts/extract_fees.py --portfolio
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from src.services.boc_pdf_pipeline import BocPdfPipeline

if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--codes", help="Comma-separated product codes")
    g.add_argument("--portfolio", action="store_true")
    p.add_argument("--ai-fallback", action="store_true")
    p.add_argument("--max-pdfs", type=int, default=1)
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()

    pipeline = BocPdfPipeline()
    codes = args.codes.split(",") if args.codes else pipeline._get_portfolio_boc_codes()

    if args.dry_run:
        print(f"Would process: {codes}"); sys.exit(0)

    results = pipeline.process_products(codes, use_ai_fallback=args.ai_fallback)
    success = [r for r in results if r.success]
    print(f"Done: {len(success)}/{len(results)} succeeded")
    output = pipeline.save_results(results)
    print(f"Saved: {output}")

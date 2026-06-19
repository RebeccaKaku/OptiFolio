"""PDF text extraction — thin wrapper around PyMuPDF.

Single responsibility: take PDF bytes, return plain text.
No business logic, no AI, no fee parsing.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from io import BytesIO
from typing import List, Optional

_log = logging.getLogger(__name__)


@dataclass
class PdfContent:
    """Extracted text from a PDF document."""

    raw_text: str                       # Full concatenated text
    pages: List[str]                    # Per-page text
    page_count: int
    file_size_bytes: int

    def find_sections(self, keyword: str, context_chars: int = 300) -> List[str]:
        """Find all occurrences of a keyword with surrounding context."""
        results: List[str] = []
        for i, page_text in enumerate(self.pages):
            idx = 0
            while True:
                idx = page_text.find(keyword, idx)
                if idx == -1:
                    break
                start = max(0, idx - 50)
                end = min(len(page_text), idx + context_chars)
                context = page_text[start:end].replace("\n", " ")
                results.append(f"[p{i+1}] {context}")
                idx += 1
        return results

    def get_fee_section(self) -> Optional[str]:
        """Heuristically locate the fee-related section.

        Searches for '产品费用' or '理财产品费用' and returns
        the most relevant contiguous block of text.
        """
        for keyword in ["产品费用", "理财产品费用", "费用"]:
            sections = self.find_sections(keyword, context_chars=800)
            if sections:
                return sections[0]
        return None


class PdfExtractor:
    """Extract text from PDF bytes using PyMuPDF (fitz).

    Usage::

        extractor = PdfExtractor()
        content = extractor.extract(pdf_bytes)
        print(content.pages[0][:200])
    """

    def extract(self, pdf_bytes: bytes) -> PdfContent:
        """Extract all text from a PDF byte buffer."""
        import fitz

        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        pages: List[str] = []
        for i in range(doc.page_count):
            text = doc[i].get_text()
            pages.append(text)
        doc.close()

        return PdfContent(
            raw_text="\n".join(pages),
            pages=pages,
            page_count=len(pages),
            file_size_bytes=len(pdf_bytes),
        )

    def extract_from_url(self, url: str, timeout: int = 30) -> PdfContent:
        """Download a PDF from URL and extract text."""
        import httpx

        resp = httpx.get(url, timeout=timeout, follow_redirects=True)
        resp.raise_for_status()
        return self.extract(resp.content)

from __future__ import annotations

from pathlib import Path

import pymupdf


def extract_pages(pdf_path: str | Path) -> list[dict]:
    """Extract text from each PDF page, preserving page boundaries."""
    path = Path(pdf_path)
    if not path.exists():
        raise FileNotFoundError(f"PDF not found: {path}")

    pages: list[dict] = []
    with pymupdf.open(path) as doc:
        for index, page in enumerate(doc, start=1):
            text = page.get_text("text") or ""
            pages.append({"page_number": index, "text": text.strip()})
    return pages

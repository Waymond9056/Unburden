from __future__ import annotations

import logging
from pathlib import Path

import pymupdf
from PIL import Image, ImageEnhance, ImageFilter, ImageOps

from app.services.ocr_cleanup import cleanup_ocr_text

logger = logging.getLogger(__name__)

_OCR_LANGUAGE = "eng"
# Render hot for camera / screen-photo pages; text PDFs never hit this path.
_OCR_RENDER_DPI = 300
# Drop FaceTime chrome (status bar / PiP / controls) before OCR.
_OCR_CROP_X = 0.07
_OCR_CROP_Y = 0.10


def extract_pages(pdf_path: str | Path) -> list[dict]:
    """Extract text from each PDF page, preserving page boundaries.

    Baseline: PyMuPDF digital text via ``get_text``.
    Fallback: Tesseract OCR on a preprocessed page image when a page has no
    embedded text (e.g. FaceTime camera-frame PDFs).
    """
    path = Path(pdf_path)
    if not path.exists():
        raise FileNotFoundError(f"PDF not found: {path}")

    pages: list[dict] = []
    with pymupdf.open(path) as doc:
        for index, page in enumerate(doc, start=1):
            text = (page.get_text("text") or "").strip()
            if not text:
                ocr_text = _ocr_page_text(page)
                # Fix Tesseract typos before retrieval / NLI (text PDFs skip this).
                text = cleanup_ocr_text(ocr_text) if ocr_text else ""
            pages.append({"page_number": index, "text": text})
    return pages


def _ocr_page_text(page: pymupdf.Page) -> str:
    """OCR a page that has no extractable digital text.

    Returns empty string if Tesseract / tessdata is unavailable so uploads
    still succeed; the UI will show no text until OCR is installed.
    """
    try:
        pix = _preprocessed_pixmap(page)
        ocr_pdf = pymupdf.open(
            stream=pix.pdfocr_tobytes(
                compress=False,
                language=_OCR_LANGUAGE,
            ),
            filetype="pdf",
        )
        try:
            text = (ocr_pdf[0].get_text("text") or "").strip()
        finally:
            ocr_pdf.close()
        return text
    except Exception as exc:  # noqa: BLE001 — keep ingest resilient without Tesseract
        logger.warning(
            "OCR fallback failed for page %s: %s",
            page.number + 1,
            exc,
        )
        return ""


def _preprocessed_pixmap(page: pymupdf.Page) -> pymupdf.Pixmap:
    """Crop FaceTime chrome and boost contrast before Tesseract."""
    raw = page.get_pixmap(dpi=_OCR_RENDER_DPI, alpha=False)
    image = Image.frombytes("RGB", (raw.width, raw.height), raw.samples)
    width, height = image.size
    image = image.crop(
        (
            int(width * _OCR_CROP_X),
            int(height * _OCR_CROP_Y),
            int(width * (1.0 - _OCR_CROP_X)),
            int(height * (1.0 - _OCR_CROP_Y)),
        )
    )
    image = ImageOps.grayscale(image)
    image = ImageOps.autocontrast(image)
    image = ImageEnhance.Contrast(image).enhance(1.6)
    image = ImageEnhance.Sharpness(image).enhance(1.8)
    image = image.filter(ImageFilter.MedianFilter(size=3))
    rgb = image.convert("RGB")
    return pymupdf.Pixmap(
        pymupdf.csRGB,
        rgb.size[0],
        rgb.size[1],
        rgb.tobytes(),
        False,
    )

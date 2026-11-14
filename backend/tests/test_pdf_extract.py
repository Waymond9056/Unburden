from pathlib import Path

import pymupdf
import pytest

from app.services.ocr_cleanup import cleanup_ocr_text
from app.services.pdf_extract import extract_pages
from app.services.seed import generate_seed_pdfs


def test_extract_pages_preserves_boundaries(tmp_path: Path) -> None:
    specs = generate_seed_pdfs(tmp_path)
    sample = next(s for s in specs if s["filename"] == "pulmonary_consult_note.pdf")
    pages = extract_pages(sample["path"])

    assert len(pages) >= 1
    assert pages[0]["page_number"] == 1
    assert "asthma" in pages[0]["text"].lower()
    assert "FICTIONAL SYNTHETIC RECORD" in pages[0]["text"]


def test_extract_pages_ocr_fallback_for_image_only_pdf(tmp_path: Path) -> None:
    try:
        pymupdf.get_tessdata()
    except Exception:
        pytest.skip("Tesseract / tessdata not available")

    # Render text to pixels, then embed only the image (no digital text layer).
    label = pymupdf.open()
    label_page = label.new_page(width=400, height=200)
    label_page.insert_text((40, 100), "Absolute Eosinophil Count", fontsize=18)
    pix = label_page.get_pixmap(dpi=150)
    label.close()

    pdf_path = tmp_path / "image_only.pdf"
    doc = pymupdf.open()
    page = doc.new_page(width=pix.width, height=pix.height)
    page.insert_image(page.rect, pixmap=pix)
    doc.save(pdf_path)
    doc.close()

    assert (pymupdf.open(pdf_path)[0].get_text("text") or "").strip() == ""
    pages = extract_pages(pdf_path)
    assert len(pages) == 1
    # Preprocess + OCR should recover the large printed label.
    assert "eosinophil" in pages[0]["text"].lower()


def test_ocr_cleanup_fixes_common_camera_typos() -> None:
    messy = (
        "atient: Raymond Yao\n"
        "sollection date: 2025-08-21\n"
        "ADsolute eosinophil count: 420 cells/yL\n"
        "sxample policy threshold of =300 cells/uL\n"
        "JrGering\n"
        "|\n"
    )
    cleaned = cleanup_ocr_text(messy)
    assert "Patient: Raymond Yao" in cleaned
    assert "Collection date" in cleaned
    assert "Absolute eosinophil count: 420 cells/µL" in cleaned
    assert "example policy threshold of ≥300" in cleaned
    assert "Ordering" in cleaned
    assert cleaned.count("|") == 0


def test_seed_set_includes_scenario_docs(tmp_path: Path) -> None:
    specs = generate_seed_pdfs(tmp_path)
    names = {s["filename"] for s in specs}
    assert "pulmonary_consult_note.pdf" in names
    assert "lab_eosinophils.pdf" not in names
    assert "duplicate_consult_summary.pdf" not in names
    assert "misleading_allergy_note.pdf" not in names

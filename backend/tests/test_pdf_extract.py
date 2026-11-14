from pathlib import Path

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


def test_seed_set_includes_scenario_docs(tmp_path: Path) -> None:
    specs = generate_seed_pdfs(tmp_path)
    names = {s["filename"] for s in specs}
    assert "pulmonary_consult_note.pdf" in names
    assert "lab_eosinophils.pdf" not in names
    assert "duplicate_consult_summary.pdf" not in names
    assert "misleading_allergy_note.pdf" not in names

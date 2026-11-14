from pathlib import Path

import pytest

from app.models.db import Document, DocumentPage
from app.services.evidence_retrieval import retrieve_page_candidates
from app.services.pdf_extract import extract_pages
from app.services.policy import REQUIREMENTS, REQUIREMENTS_BY_ID
from app.services.seed import generate_seed_pdfs


@pytest.mark.parametrize(
    "filename",
    [
        "pulmonary_consult_note.pdf",
        "medication_history.pdf",
        "exacerbation_er_note.pdf",
        "lab_eosinophils.pdf",
        "duplicate_consult_summary.pdf",
        "misleading_allergy_note.pdf",
    ],
)
def test_retrieved_candidates_keep_exact_page_citations(
    tmp_path: Path, filename: str
) -> None:
    specs = generate_seed_pdfs(tmp_path)
    spec = next(item for item in specs if item["filename"] == filename)
    extracted_pages = extract_pages(spec["path"])
    document = Document(
        id="test-document",
        patient_id="test-patient",
        filename=filename,
        original_filename=filename,
        document_type=spec["document_type"],
        storage_path=str(spec["path"]),
        page_count=len(extracted_pages),
    )

    candidates = []
    for raw_page in extracted_pages:
        page = DocumentPage(
            document_id=document.id,
            page_number=raw_page["page_number"],
            text=raw_page["text"],
        )
        candidates.extend(
            candidate
            for requirement in REQUIREMENTS
            for candidate in retrieve_page_candidates(
                document=document,
                page=page,
                requirement=requirement,
            )
        )
        assert all(candidate.supporting_quote in page.text for candidate in candidates)

    assert candidates
    assert all(item.verification_status == "unverified_candidate" for item in candidates)


def test_lab_retrieval_extracts_only_requirement_details() -> None:
    requirement = REQUIREMENTS_BY_ID["qualifying_eosinophil_result"]
    page = DocumentPage(
        document_id="doc",
        page_number=3,
        text="Collection date: 2025-08-21. Absolute eosinophil count: 420 cells/µL.",
    )
    document = Document(
        id="doc",
        patient_id="patient",
        filename="lab.pdf",
        original_filename="lab.pdf",
        document_type="laboratory_report",
        storage_path="/tmp/lab.pdf",
        page_count=1,
    )

    candidates = retrieve_page_candidates(
        document=document,
        page=page,
        requirement=requirement,
    )

    assert len(candidates) == 1
    assert candidates[0].requirement_id == requirement.id
    assert candidates[0].supporting_quote == (
        "Collection date: 2025-08-21. Absolute eosinophil count: 420 cells/µL."
    )
    assert '"dates": ["2025-08-21"]' in candidates[0].extracted_details_json
    assert "diagnosis" not in candidates[0].extracted_details_json


def test_nonmatching_passage_creates_no_general_medical_record() -> None:
    page = DocumentPage(
        document_id="doc",
        page_number=1,
        text="The patient received an influenza vaccination today.",
    )
    document = Document(
        id="doc",
        patient_id="patient",
        filename="visit.pdf",
        original_filename="visit.pdf",
        document_type="clinical_note",
        storage_path="/tmp/visit.pdf",
        page_count=1,
    )

    candidates = [
        candidate
        for requirement in REQUIREMENTS
        for candidate in retrieve_page_candidates(
            document=document,
            page=page,
            requirement=requirement,
        )
    ]

    assert candidates == []

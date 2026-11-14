from datetime import date
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base
from app.models.db import Document, DocumentPage, EvidenceCandidate, Patient
from app.services.evidence_retrieval import retrieve_for_document
from app.services.evidence_verification import (
    STATUS_NEEDS_REVIEW,
    STATUS_NOT_ESTABLISHED,
    STATUS_SUPPORTED,
    evaluate_patient_policy,
    verify_candidate,
)
from app.services.policy import REQUIREMENTS_BY_ID, load_policy
from app.services.pdf_extract import extract_pages
from app.services.seed import generate_seed_pdfs


def _memory_session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine, autocommit=False, autoflush=False)()


def test_policy_loads_fictional_constraints() -> None:
    policy = load_policy()
    assert "FICTIONAL" in policy.disclaimer.upper() or "fictional" in policy.name.lower()
    assert policy.logic == "AND"
    assert len(policy.requirements) == 4
    lab = REQUIREMENTS_BY_ID["qualifying_eosinophil_result"]
    assert lab.numeric is not None
    assert lab.numeric.min_value == 300
    assert lab.temporal is not None
    assert lab.temporal.within_months == 12


def test_quote_must_exist_in_source_page() -> None:
    db = _memory_session()
    db.add(Patient(id="p1", display_name="Raymond Yao", date_of_birth=date(1985, 3, 12)))
    db.add(
        Document(
            id="d1",
            patient_id="p1",
            filename="note.pdf",
            original_filename="note.pdf",
            document_type="clinical_note",
            storage_path="/tmp/note.pdf",
            page_count=1,
        )
    )
    db.add(DocumentPage(document_id="d1", page_number=1, text="Severe persistent asthma noted."))
    candidate = EvidenceCandidate(
        id="c1",
        patient_id="p1",
        document_id="d1",
        policy_id="fictional-severe-asthma-policy",
        requirement_id="documented_severe_asthma",
        source_page=1,
        supporting_quote="Invented quotation that is not on the page",
        extracted_details_json="{}",
        relevance_score=0.9,
        retrieval_method="lexical",
        verification_status="unverified_candidate",
    )
    db.add(candidate)
    db.commit()
    candidate.document = db.get(Document, "d1")

    verdict = verify_candidate(
        db,
        candidate,
        REQUIREMENTS_BY_ID["documented_severe_asthma"],
        as_of_date=date(2025, 11, 1),
    )
    assert verdict.status == "rejected"
    assert "not found" in verdict.reasons[0].lower()


def test_temporal_and_numeric_lab_rules() -> None:
    db = _memory_session()
    db.add(Patient(id="p1", display_name="Raymond Yao", date_of_birth=date(1985, 3, 12)))
    db.add(
        Document(
            id="lab",
            patient_id="p1",
            filename="lab.pdf",
            original_filename="lab.pdf",
            document_type="laboratory_report",
            storage_path="/tmp/lab.pdf",
            page_count=1,
        )
    )
    text = "Collection date: 2025-08-21. Absolute eosinophil count: 420 cells/µL."
    db.add(DocumentPage(document_id="lab", page_number=1, text=text))
    candidate = EvidenceCandidate(
        id="c-lab",
        patient_id="p1",
        document_id="lab",
        policy_id="fictional-severe-asthma-policy",
        requirement_id="qualifying_eosinophil_result",
        source_page=1,
        supporting_quote=text,
        extracted_details_json='{"dates":["2025-08-21"],"numeric_mentions":["420 cells/µL"]}',
        relevance_score=0.9,
        retrieval_method="lexical",
        verification_status="unverified_candidate",
    )
    db.add(candidate)
    db.commit()
    candidate.document = db.get(Document, "lab")

    ok = verify_candidate(
        db,
        candidate,
        REQUIREMENTS_BY_ID["qualifying_eosinophil_result"],
        as_of_date=date(2025, 11, 1),
    )
    assert ok.status == "accepted"

    stale = EvidenceCandidate(
        id="c-old",
        patient_id="p1",
        document_id="lab",
        policy_id="fictional-severe-asthma-policy",
        requirement_id="qualifying_eosinophil_result",
        source_page=1,
        supporting_quote=text.replace("2025-08-21", "2023-01-01"),
        extracted_details_json='{"dates":["2023-01-01"],"numeric_mentions":["420 cells/µL"]}',
        relevance_score=0.9,
        retrieval_method="lexical",
        verification_status="unverified_candidate",
    )
    # Quote won't be in page — use page text that includes stale date for this unit check
    db.add(
        DocumentPage(
            document_id="lab",
            page_number=2,
            text="Collection date: 2023-01-01. Absolute eosinophil count: 420 cells/µL.",
        )
    )
    stale.source_page = 2
    stale.supporting_quote = "Collection date: 2023-01-01. Absolute eosinophil count: 420 cells/µL."
    db.add(stale)
    db.commit()
    stale.document = db.get(Document, "lab")
    old = verify_candidate(
        db,
        stale,
        REQUIREMENTS_BY_ID["qualifying_eosinophil_result"],
        as_of_date=date(2025, 11, 1),
    )
    assert old.status == "rejected"


def test_and_or_requirement_rollups() -> None:
    db = _memory_session()
    patient = Patient(id="p-and", display_name="Raymond Yao", date_of_birth=date(1985, 3, 12))
    db.add(patient)
    db.commit()

    # No candidates → all NOT_ESTABLISHED under AND
    empty = evaluate_patient_policy(db, "p-and", persist=False)
    assert empty.overall_status == STATUS_NOT_ESTABLISHED
    assert all(item.status == STATUS_NOT_ESTABLISHED for item in empty.requirements)


def test_seed_corpus_evaluation_supports_complete_set(tmp_path: Path) -> None:
    db = _memory_session()
    # Point seed dir via generating PDFs then manually indexing like seed_database
    from app.core.config import get_settings
    from app.services.seed import PATIENT_ID, PATIENT_NAME, PATIENT_DOB

    settings = get_settings()
    settings.__dict__  # touch
    db.add(Patient(id=PATIENT_ID, display_name=PATIENT_NAME, date_of_birth=PATIENT_DOB))
    db.commit()

    specs = generate_seed_pdfs(tmp_path)
    for spec in specs:
        pages = extract_pages(spec["path"])
        doc = Document(
            id=spec["filename"],
            patient_id=PATIENT_ID,
            filename=spec["filename"],
            original_filename=spec["filename"],
            document_type=spec["document_type"],
            storage_path=str(spec["path"]),
            page_count=len(pages),
            source_label=spec["source_label"],
            scenario_tag=spec.get("scenario_tag"),
        )
        db.add(doc)
        for page in pages:
            db.add(
                DocumentPage(
                    document_id=doc.id,
                    page_number=page["page_number"],
                    text=page["text"],
                )
            )
        db.commit()
        retrieve_for_document(db, doc)

    evaluation = evaluate_patient_policy(db, PATIENT_ID, persist=True)
    by_id = {item.requirement_id: item for item in evaluation.requirements}

    assert by_id["documented_severe_asthma"].status == STATUS_SUPPORTED
    assert by_id["prior_controller_therapy"].status == STATUS_SUPPORTED
    assert by_id["qualifying_eosinophil_result"].status == STATUS_SUPPORTED
    assert by_id["recent_exacerbation_history"].status == STATUS_SUPPORTED
    assert evaluation.overall_status == STATUS_SUPPORTED


def test_missing_lab_is_not_established_or_review_without_quant_lab(tmp_path: Path) -> None:
    db = _memory_session()
    from app.services.seed import PATIENT_ID, PATIENT_NAME, PATIENT_DOB

    db.add(Patient(id=PATIENT_ID, display_name=PATIENT_NAME, date_of_birth=PATIENT_DOB))
    db.commit()
    specs = generate_seed_pdfs(tmp_path)
    for spec in specs:
        if spec["filename"] == "lab_eosinophils.pdf":
            continue
        pages = extract_pages(spec["path"])
        doc = Document(
            id=spec["filename"],
            patient_id=PATIENT_ID,
            filename=spec["filename"],
            original_filename=spec["filename"],
            document_type=spec["document_type"],
            storage_path=str(spec["path"]),
            page_count=len(pages),
            source_label=spec["source_label"],
        )
        db.add(doc)
        for page in pages:
            db.add(
                DocumentPage(
                    document_id=doc.id,
                    page_number=page["page_number"],
                    text=page["text"],
                )
            )
        db.commit()
        retrieve_for_document(db, doc)

    evaluation = evaluate_patient_policy(db, PATIENT_ID, persist=True)
    lab = next(item for item in evaluation.requirements if item.requirement_id == "qualifying_eosinophil_result")
    assert lab.status in {STATUS_NOT_ESTABLISHED, STATUS_NEEDS_REVIEW}
    assert evaluation.overall_status != STATUS_SUPPORTED

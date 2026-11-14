from datetime import date

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base
from app.models.db import Document, DocumentPage, EvidenceCandidate, Patient
from app.services.evidence_packet import build_evidence_packet
from app.services.evidence_verification import (
    CANDIDATE_SUPPORT,
    STATUS_READY,
    STATUS_NEEDS_REVIEW,
    RequirementEvaluation,
    PolicyEvaluation,
)
from app.services.policy import FICTIONAL_POLICY_ID


def _session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine, autocommit=False, autoflush=False)()


def _seed_patient(db):
    db.add(Patient(id="p1", display_name="Raymond Yao", date_of_birth=date(1985, 3, 12)))
    db.commit()


def _add_doc(db, *, doc_id: str, doc_type: str, pages: int = 1, label: str | None = None):
    doc = Document(
        id=doc_id,
        patient_id="p1",
        filename=f"{doc_id}.pdf",
        original_filename=f"{doc_id}.pdf",
        document_type=doc_type,
        storage_path=f"/tmp/{doc_id}.pdf",
        page_count=pages,
        source_label=label or doc_id,
    )
    db.add(doc)
    for page in range(1, pages + 1):
        db.add(DocumentPage(document_id=doc_id, page_number=page, text=f"page {page}"))
    db.commit()
    return doc


def _add_accepted(
    db,
    *,
    candidate_id: str,
    doc_id: str,
    requirement_id: str,
    relevance: float,
):
    db.add(
        EvidenceCandidate(
            id=candidate_id,
            patient_id="p1",
            document_id=doc_id,
            policy_id=FICTIONAL_POLICY_ID,
            requirement_id=requirement_id,
            source_page=1,
            supporting_quote=f"quote for {requirement_id}",
            extracted_details_json="{}",
            relevance_score=relevance,
            retrieval_method="lexical",
            verification_status=CANDIDATE_SUPPORT,
        )
    )
    db.commit()


def _evaluation_for(supported_map: dict[str, list[str]]) -> PolicyEvaluation:
    """supported_map: requirement_id -> support candidate ids."""
    requirements = []
    for req_id, candidate_ids in supported_map.items():
        requirements.append(
            RequirementEvaluation(
                requirement_id=req_id,
                title=req_id,
                status=STATUS_READY if candidate_ids else STATUS_NEEDS_REVIEW,
                explanation="",
                suggested_document_types=["lab report"],
                support_candidate_ids=candidate_ids,
                insufficient_candidate_ids=[],
                contradiction_candidate_ids=[],
            )
        )
    # Fill remaining policy requirements as contradiction so packet only covers support.
    known = set(supported_map)
    for req_id in (
        "documented_severe_asthma",
        "prior_controller_therapy",
        "qualifying_eosinophil_result",
    ):
        if req_id in known:
            continue
        requirements.append(
            RequirementEvaluation(
                requirement_id=req_id,
                title=req_id,
                status=STATUS_NEEDS_REVIEW,
                explanation="",
                suggested_document_types=["relevant clinical document"],
                support_candidate_ids=[],
                insufficient_candidate_ids=[],
                contradiction_candidate_ids=[],
            )
        )
    return PolicyEvaluation(
        policy_id=FICTIONAL_POLICY_ID,
        policy_name="Test policy",
        disclaimer="FICTIONAL",
        as_of_date=date(2025, 11, 1),
        logic="AND",
        overall_status=STATUS_READY,
        requirements=requirements,
        candidate_verdicts=[],
    )


def test_prefers_stronger_source_over_merely_smaller_set():
    """A short weak note should lose to a stronger primary source even if more pages."""
    db = _session()
    _seed_patient(db)
    _add_doc(db, doc_id="weak-note", doc_type="clinical_note", pages=1, label="Weak note")
    _add_doc(db, doc_id="lab-report", doc_type="laboratory_report", pages=3, label="Lab EOS")
    _add_accepted(
        db,
        candidate_id="c-weak",
        doc_id="weak-note",
        requirement_id="qualifying_eosinophil_result",
        relevance=0.4,
    )
    _add_accepted(
        db,
        candidate_id="c-lab",
        doc_id="lab-report",
        requirement_id="qualifying_eosinophil_result",
        relevance=0.9,
    )

    evaluation = _evaluation_for(
        {"qualifying_eosinophil_result": ["c-weak", "c-lab"]}
    )
    packet = build_evidence_packet(db, "p1", evaluation=evaluation)
    selected = {doc.document_id for doc in packet.selected_documents}

    assert "lab-report" in selected
    assert "weak-note" not in selected
    assert packet.total_pages == 3


def test_omits_redundant_duplicate_when_primary_sources_cover():
    db = _session()
    _seed_patient(db)
    _add_doc(db, doc_id="consult", doc_type="clinical_note", pages=1, label="Consult")
    _add_doc(db, doc_id="duplicate", doc_type="clinical_note", pages=1, label="Duplicate")
    _add_doc(db, doc_id="meds", doc_type="medication_record", pages=1, label="Meds")
    _add_accepted(
        db, candidate_id="c1", doc_id="consult", requirement_id="documented_severe_asthma", relevance=0.8
    )
    _add_accepted(
        db, candidate_id="c2", doc_id="duplicate", requirement_id="documented_severe_asthma", relevance=0.5
    )
    _add_accepted(
        db, candidate_id="c3", doc_id="meds", requirement_id="prior_controller_therapy", relevance=0.9
    )

    evaluation = _evaluation_for(
        {
            "documented_severe_asthma": ["c1", "c2"],
            "prior_controller_therapy": ["c3"],
        }
    )
    packet = build_evidence_packet(db, "p1", evaluation=evaluation)
    selected = {doc.document_id for doc in packet.selected_documents}
    assert "consult" in selected
    assert "meds" in selected
    assert "duplicate" in packet.omitted_document_ids


def test_missing_checklist_from_not_established():
    db = _session()
    _seed_patient(db)
    _add_doc(db, doc_id="consult", doc_type="clinical_note", pages=1)
    _add_accepted(
        db, candidate_id="c1", doc_id="consult", requirement_id="documented_severe_asthma", relevance=0.8
    )
    evaluation = _evaluation_for({"documented_severe_asthma": ["c1"]})
    packet = build_evidence_packet(db, "p1", evaluation=evaluation)
    missing_ids = {item.requirement_id for item in packet.missing_evidence}
    assert "qualifying_eosinophil_result" in missing_ids
    assert "documented_severe_asthma" not in missing_ids
    lab_missing = next(
        item for item in packet.missing_evidence if item.requirement_id == "qualifying_eosinophil_result"
    )
    assert lab_missing.suggested_document_types

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base
from app.models.db import Document, DocumentPage, EvidenceCandidate, Patient
from app.services.evidence_verification import verify_candidate
from app.services.nli_deberta import (
    interpret_nli_verification_signal,
    ml_dependencies_available,
)
from app.services.policy import REQUIREMENTS_BY_ID

ARCH_BENCHMARK = (
    Path(__file__).resolve().parents[1]
    / "benchmarks"
    / "verification_architecture_benchmark.json"
)


def _session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine, autocommit=False, autoflush=False)()


def _candidate(db, *, requirement_id: str, document_type: str, quote: str):
    patient_id = "p-arch"
    doc_id = f"d-{uuid4().hex[:8]}"
    if db.get(Patient, patient_id) is None:
        db.add(Patient(id=patient_id, display_name="Arch", date_of_birth=date(1985, 3, 12)))
    db.add(
        Document(
            id=doc_id,
            patient_id=patient_id,
            filename=f"{doc_id}.pdf",
            original_filename=f"{doc_id}.pdf",
            document_type=document_type,
            storage_path=f"/tmp/{doc_id}.pdf",
            page_count=1,
        )
    )
    db.add(DocumentPage(document_id=doc_id, page_number=1, text=quote))
    candidate = EvidenceCandidate(
        id=str(uuid4()),
        patient_id=patient_id,
        document_id=doc_id,
        policy_id="fictional-severe-asthma-policy",
        requirement_id=requirement_id,
        source_page=1,
        supporting_quote=quote,
        extracted_details_json="{}",
        relevance_score=0.9,
        retrieval_method="lexical",
        verification_status="unverified_candidate",
    )
    db.add(candidate)
    db.commit()
    candidate.document = db.get(Document, doc_id)
    return candidate


def test_architecture_benchmark_file_is_well_formed() -> None:
    payload = json.loads(ARCH_BENCHMARK.read_text(encoding="utf-8"))
    assert len(payload["cases"]) >= 10
    for case in payload["cases"]:
        assert case["requirement_id"] in REQUIREMENTS_BY_ID
        assert case["gold_status"] in {"accepted", "rejected", "needs_review"}


def test_use_nli_false_matches_default_deterministic_path() -> None:
    db = _session()
    quote = (
        "Severe persistent asthma has been ruled out. Current diagnosis is vocal cord "
        "dysfunction only. J45.50 was removed from the problem list."
    )
    candidate = _candidate(
        db,
        requirement_id="documented_severe_asthma",
        document_type="clinical_note",
        quote=quote,
    )
    requirement = REQUIREMENTS_BY_ID["documented_severe_asthma"]
    off = verify_candidate(
        db, candidate, requirement, as_of_date=date(2025, 11, 1), use_nli=False
    )
    # Keyword path still sees "severe persistent asthma" / J45.50 without NLI.
    assert off.status == "accepted"


def test_interpret_nli_signal_strong_contradiction_rejects() -> None:
    from app.services.nli_deberta import NliScore

    score = NliScore(
        premise="x",
        hypothesis="y",
        entailment=0.05,
        neutral=0.10,
        contradiction=0.85,
        predicted_label="contradiction",
        model_name="test",
    )
    signal = interpret_nli_verification_signal(score)
    assert signal.action == "reject"


def test_interpret_nli_signal_strong_entailment_is_note_only() -> None:
    from app.services.nli_deberta import NliScore

    score = NliScore(
        premise="x",
        hypothesis="y",
        entailment=0.92,
        neutral=0.05,
        contradiction=0.03,
        predicted_label="entailment",
        model_name="test",
    )
    signal = interpret_nli_verification_signal(score)
    assert signal.action == "support_note"


@pytest.mark.skipif(
    not ml_dependencies_available(),
    reason="optional ML deps (torch/transformers) not installed",
)
def test_m3_plus_deberta_rejects_paraphrased_asthma_negation() -> None:
    db = _session()
    quote = (
        "Severe persistent asthma has been ruled out. Current diagnosis is vocal cord "
        "dysfunction only. J45.50 was removed from the problem list."
    )
    candidate = _candidate(
        db,
        requirement_id="documented_severe_asthma",
        document_type="clinical_note",
        quote=quote,
    )
    requirement = REQUIREMENTS_BY_ID["documented_severe_asthma"]
    m3 = verify_candidate(
        db, candidate, requirement, as_of_date=date(2025, 11, 1), use_nli=False
    )
    combo = verify_candidate(
        db, candidate, requirement, as_of_date=date(2025, 11, 1), use_nli=True
    )
    assert m3.status == "accepted"
    assert combo.status in {"rejected", "needs_review"}
    assert "deberta" in combo.reasons[0].lower() or "nli" in combo.reasons[0].lower()


@pytest.mark.skipif(
    not ml_dependencies_available(),
    reason="optional ML deps (torch/transformers) not installed",
)
def test_m3_plus_deberta_still_rejects_below_threshold_via_math() -> None:
    db = _session()
    quote = "Collection date: 2025-08-21. Absolute eosinophil count: 180 cells/µL."
    candidate = _candidate(
        db,
        requirement_id="qualifying_eosinophil_result",
        document_type="laboratory_report",
        quote=quote,
    )
    requirement = REQUIREMENTS_BY_ID["qualifying_eosinophil_result"]
    combo = verify_candidate(
        db, candidate, requirement, as_of_date=date(2025, 11, 1), use_nli=True
    )
    # If NLI does not short-circuit, math must still reject 180 < 300.
    assert combo.status in {"rejected", "needs_review"}
    if combo.status == "rejected" and "nli" not in combo.reasons[0].lower():
        assert "300" in combo.reasons[0] or "180" in combo.reasons[0]

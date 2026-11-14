from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.db import EvidenceCandidate, Patient
from app.models.schemas import (
    CandidateVerdictOut,
    DocumentDetail,
    DocumentSummary,
    EvidenceCandidateOut,
    PageText,
    PatientOut,
    PolicyEvaluationOut,
    RequirementEvaluationOut,
)
from app.services import documents as document_service
from app.services.evidence_retrieval import retrieve_for_patient
from app.services.evidence_verification import evaluate_patient_policy
from app.services.policy import FICTIONAL_POLICY_ID, REQUIREMENTS_BY_ID

router = APIRouter(prefix="/patients", tags=["patients"])


def _document_summary(doc) -> DocumentSummary:
    return DocumentSummary(
        id=doc.id,
        patient_id=doc.patient_id,
        filename=doc.filename,
        original_filename=doc.original_filename,
        document_type=doc.document_type,
        page_count=doc.page_count,
        uploaded_at=doc.uploaded_at,
        source_label=doc.source_label,
        scenario_tag=doc.scenario_tag,
    )


@router.get("", response_model=list[PatientOut])
def list_patients(db: Session = Depends(get_db)) -> list[Patient]:
    return db.query(Patient).order_by(Patient.display_name).all()


@router.get("/{patient_id}", response_model=PatientOut)
def get_patient(patient_id: str, db: Session = Depends(get_db)) -> Patient:
    return document_service.ensure_patient(db, patient_id)


@router.post("/{patient_id}/documents", response_model=DocumentSummary)
async def upload_document(
    patient_id: str,
    file: UploadFile = File(...),
    document_type: str = Form(default=""),
    source_label: str | None = Form(default=None),
    db: Session = Depends(get_db),
) -> DocumentSummary:
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF uploads are supported")

    document = document_service.store_and_index_pdf(
        db,
        patient_id=patient_id,
        upload=file,
        document_type=document_type.strip(),
        source_label=source_label,
    )
    return _document_summary(document)


@router.get("/{patient_id}/documents", response_model=list[DocumentSummary])
def list_documents(patient_id: str, db: Session = Depends(get_db)) -> list[DocumentSummary]:
    docs = document_service.list_documents(db, patient_id)
    return [_document_summary(d) for d in docs]


@router.get("/{patient_id}/documents/{document_id}", response_model=DocumentDetail)
def get_document(patient_id: str, document_id: str, db: Session = Depends(get_db)) -> DocumentDetail:
    doc = document_service.get_document(db, patient_id, document_id)
    return DocumentDetail(
        **_document_summary(doc).model_dump(),
        pages=[PageText(page_number=p.page_number, text=p.text) for p in doc.pages],
    )


@router.get("/{patient_id}/documents/{document_id}/file")
def download_document_file(
    patient_id: str, document_id: str, db: Session = Depends(get_db)
) -> FileResponse:
    doc = document_service.get_document(db, patient_id, document_id)
    path = Path(doc.storage_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Stored PDF file is missing")
    return FileResponse(
        path=path,
        media_type="application/pdf",
        filename=doc.original_filename,
        content_disposition_type="inline",
    )


def _candidate_out(candidate: EvidenceCandidate) -> EvidenceCandidateOut:
    requirement = REQUIREMENTS_BY_ID[candidate.requirement_id]
    return EvidenceCandidateOut(
        id=candidate.id,
        patient_id=candidate.patient_id,
        document_id=candidate.document_id,
        policy_id=candidate.policy_id,
        requirement_id=candidate.requirement_id,
        requirement_title=requirement.title,
        source_page=candidate.source_page,
        supporting_quote=candidate.supporting_quote,
        extracted_details=json.loads(candidate.extracted_details_json),
        relevance_score=candidate.relevance_score,
        retrieval_method=candidate.retrieval_method,
        verification_status=candidate.verification_status,
        created_at=candidate.created_at,
        source_document_name=(
            candidate.document.source_label or candidate.document.original_filename
        ),
        source_document_type=candidate.document.document_type,
    )


@router.get("/{patient_id}/evidence-candidates", response_model=list[EvidenceCandidateOut])
def list_evidence_candidates(
    patient_id: str,
    requirement_id: str | None = None,
    db: Session = Depends(get_db),
) -> list[EvidenceCandidateOut]:
    document_service.ensure_patient(db, patient_id)
    query = db.query(EvidenceCandidate).filter(
        EvidenceCandidate.patient_id == patient_id,
        EvidenceCandidate.policy_id == FICTIONAL_POLICY_ID,
    )
    if requirement_id:
        if requirement_id not in REQUIREMENTS_BY_ID:
            raise HTTPException(status_code=404, detail="Policy requirement not found")
        query = query.filter(EvidenceCandidate.requirement_id == requirement_id)
    candidates = query.order_by(
        EvidenceCandidate.requirement_id,
        EvidenceCandidate.relevance_score.desc(),
        EvidenceCandidate.created_at,
    ).all()
    return [_candidate_out(candidate) for candidate in candidates]


@router.post("/{patient_id}/evidence-candidates/retrieve", response_model=list[EvidenceCandidateOut])
def retrieve_evidence_candidates(
    patient_id: str, db: Session = Depends(get_db)
) -> list[EvidenceCandidateOut]:
    document_service.ensure_patient(db, patient_id)
    return [
        _candidate_out(candidate)
        for candidate in retrieve_for_patient(db, patient_id)
    ]


def _policy_evaluation_out(patient_id: str, evaluation, db: Session) -> PolicyEvaluationOut:
    candidates = (
        db.query(EvidenceCandidate)
        .filter(
            EvidenceCandidate.patient_id == patient_id,
            EvidenceCandidate.policy_id == evaluation.policy_id,
        )
        .all()
    )
    by_id = {candidate.id: _candidate_out(candidate) for candidate in candidates}
    return PolicyEvaluationOut(
        patient_id=patient_id,
        policy_id=evaluation.policy_id,
        policy_name=evaluation.policy_name,
        disclaimer=evaluation.disclaimer,
        as_of_date=evaluation.as_of_date,
        logic=evaluation.logic,
        overall_status=evaluation.overall_status,
        requirements=[
            RequirementEvaluationOut(
                requirement_id=item.requirement_id,
                title=item.title,
                status=item.status,
                explanation=item.explanation,
                suggested_document_types=item.suggested_document_types,
                accepted_candidate_ids=item.accepted_candidate_ids,
                review_candidate_ids=item.review_candidate_ids,
                rejected_candidate_ids=item.rejected_candidate_ids,
                supporting_candidates=[
                    by_id[candidate_id]
                    for candidate_id in item.accepted_candidate_ids
                    if candidate_id in by_id
                ],
                review_candidates=[
                    by_id[candidate_id]
                    for candidate_id in item.review_candidate_ids
                    if candidate_id in by_id
                ],
            )
            for item in evaluation.requirements
        ],
        candidate_verdicts=[
            CandidateVerdictOut(
                candidate_id=verdict.candidate_id,
                status=verdict.status,
                reasons=verdict.reasons,
            )
            for verdict in evaluation.candidate_verdicts
        ],
    )


@router.post("/{patient_id}/evaluate", response_model=PolicyEvaluationOut)
def evaluate_policy(
    patient_id: str,
    policy_id: str = FICTIONAL_POLICY_ID,
    db: Session = Depends(get_db),
) -> PolicyEvaluationOut:
    document_service.ensure_patient(db, patient_id)
    if policy_id != FICTIONAL_POLICY_ID:
        raise HTTPException(status_code=404, detail="Policy not found")
    evaluation = evaluate_patient_policy(db, patient_id, policy_id=policy_id, persist=True)
    return _policy_evaluation_out(patient_id, evaluation, db)


@router.get("/{patient_id}/policy-evaluation", response_model=PolicyEvaluationOut)
def get_policy_evaluation(
    patient_id: str,
    policy_id: str = FICTIONAL_POLICY_ID,
    db: Session = Depends(get_db),
) -> PolicyEvaluationOut:
    """Re-run structured verification (deterministic) and return the checklist."""
    document_service.ensure_patient(db, patient_id)
    if policy_id != FICTIONAL_POLICY_ID:
        raise HTTPException(status_code=404, detail="Policy not found")
    evaluation = evaluate_patient_policy(db, patient_id, policy_id=policy_id, persist=True)
    return _policy_evaluation_out(patient_id, evaluation, db)



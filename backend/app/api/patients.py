from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response
from sqlalchemy.orm import Session, joinedload

from app.core.database import get_db
from app.models.db import EvidenceCandidate, Patient
from app.models.schemas import (
    CandidateNliOut,
    CandidateStatusUpdate,
    CandidateVerdictOut,
    DocumentDetail,
    DocumentSummary,
    EvidenceCandidateOut,
    EvidencePacketOut,
    MissingEvidenceOut,
    NliCandidateScoreOut,
    NliScoreBatchOut,
    PageText,
    PacketDocumentOut,
    PatientOut,
    PolicyEvaluationOut,
    RequirementEvaluationOut,
)
from app.services import documents as document_service
from app.services.evidence_packet import build_evidence_packet
from app.services.evidence_retrieval import retrieve_for_patient
from app.services.evidence_verification import (
    clinician_override_status,
    display_status_for_candidate,
    evaluate_patient_policy,
    model_status_for_candidate,
    set_clinician_override,
)
from app.services.nli_deberta import (
    DEFAULT_MODEL_NAME,
    NliDependenciesMissing,
    lexical_support_label,
    requirement_hypothesis,
    score_requirement_passage,
)
from app.services.packet_export import export_evidence_packet_pdf
from app.services.policy import (
    FICTIONAL_POLICY_ID,
    REQUIREMENTS_BY_ID,
    known_policy_id,
)
from app.services.status_vocab import canonicalize_status

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


@router.delete("/{patient_id}/documents/{document_id}", status_code=204)
def delete_document(
    patient_id: str, document_id: str, db: Session = Depends(get_db)
) -> None:
    document_service.delete_document(db, patient_id, document_id)


def _nli_out_from_details(details: dict) -> CandidateNliOut | None:
    raw = details.get("nli")
    if not isinstance(raw, dict):
        return None
    try:
        support = float(
            raw.get(
                "support",
                raw.get("entailment", raw.get("support_probability")),
            )
        )
        insufficient = float(raw.get("insufficient", raw.get("neutral")))
        contradiction = float(raw["contradiction"])
        predicted = canonicalize_status(str(raw.get("predicted_label") or "")) or str(
            raw.get("predicted_label") or ""
        )
        return CandidateNliOut(
            support_probability=float(raw.get("support_probability", support)),
            support=support,
            insufficient=insufficient,
            contradiction=contradiction,
            entailment=support,
            neutral=insufficient,
            predicted_label=predicted,
            model_name=str(raw.get("model_name") or DEFAULT_MODEL_NAME),
        )
    except (KeyError, TypeError, ValueError):
        return None


def _candidate_out(candidate: EvidenceCandidate) -> EvidenceCandidateOut:
    requirement = REQUIREMENTS_BY_ID.get(candidate.requirement_id)
    try:
        details = json.loads(candidate.extracted_details_json or "{}")
    except json.JSONDecodeError:
        details = {}
    if not isinstance(details, dict):
        details = {}
    status = (
        canonicalize_status(candidate.verification_status)
        or candidate.verification_status
    )
    return EvidenceCandidateOut(
        id=candidate.id,
        patient_id=candidate.patient_id,
        document_id=candidate.document_id,
        policy_id=candidate.policy_id,
        requirement_id=candidate.requirement_id,
        requirement_title=(
            requirement.title if requirement else candidate.requirement_id
        ),
        source_page=candidate.source_page,
        supporting_quote=candidate.supporting_quote,
        extracted_details=details,
        relevance_score=candidate.relevance_score,
        retrieval_method=candidate.retrieval_method,
        verification_status=status,
        created_at=candidate.created_at,
        source_document_name=(
            candidate.document.source_label or candidate.document.original_filename
        ),
        source_document_type=candidate.document.document_type,
        nli=_nli_out_from_details(details),
        display_status=display_status_for_candidate(candidate),
        model_status=model_status_for_candidate(candidate),
        clinician_override=clinician_override_status(candidate),
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


@router.patch(
    "/{patient_id}/evidence-candidates/{candidate_id}/status",
    response_model=EvidenceCandidateOut,
)
def update_candidate_status(
    patient_id: str,
    candidate_id: str,
    body: CandidateStatusUpdate,
    db: Session = Depends(get_db),
) -> EvidenceCandidateOut:
    """Clinician override of a citation status after manual review."""
    document_service.ensure_patient(db, patient_id)
    candidate = (
        db.query(EvidenceCandidate)
        .options(joinedload(EvidenceCandidate.document))
        .filter(
            EvidenceCandidate.id == candidate_id,
            EvidenceCandidate.patient_id == patient_id,
        )
        .first()
    )
    if candidate is None:
        raise HTTPException(status_code=404, detail="Evidence candidate not found")
    try:
        set_clinician_override(candidate, body.status)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    db.commit()
    db.refresh(candidate)
    return _candidate_out(candidate)


@router.post(
    "/{patient_id}/evidence-candidates/nli-score",
    response_model=NliScoreBatchOut,
)
def score_evidence_candidates_nli(
    patient_id: str,
    requirement_id: str | None = None,
    db: Session = Depends(get_db),
) -> NliScoreBatchOut:
    """Experimental DeBERTa NLI scores for retrieved candidates.

    Does not change verification_status or Milestone 3 decisions.
    """
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

    scores: list[NliCandidateScoreOut] = []
    try:
        for candidate in candidates:
            requirement = REQUIREMENTS_BY_ID[candidate.requirement_id]
            nli = score_requirement_passage(candidate.supporting_quote, requirement)
            scores.append(
                NliCandidateScoreOut(
                    candidate_id=candidate.id,
                    requirement_id=candidate.requirement_id,
                    requirement_title=requirement.title,
                    premise=nli.premise,
                    hypothesis=nli.hypothesis,
                    support=nli.support,
                    insufficient=nli.insufficient,
                    contradiction=nli.contradiction,
                    entailment=nli.support,
                    neutral=nli.insufficient,
                    predicted_label=nli.predicted_label,
                    lexical_baseline_label=lexical_support_label(
                        candidate.supporting_quote, requirement
                    ),
                    verification_status=(
                        canonicalize_status(candidate.verification_status)
                        or candidate.verification_status
                    ),
                    model_name=nli.model_name,
                )
            )
    except NliDependenciesMissing as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    return NliScoreBatchOut(
        patient_id=patient_id,
        model_name=DEFAULT_MODEL_NAME,
        note=(
            "Experimental zero-shot DeBERTa NLI scores only. "
            "Raw entailment is not a calibrated probability and does not override "
            "deterministic verification."
        ),
        scores=scores,
    )


def _policy_evaluation_out(patient_id: str, evaluation, db: Session) -> PolicyEvaluationOut:
    requirement_ids = [item.requirement_id for item in evaluation.requirements]
    candidates = (
        db.query(EvidenceCandidate)
        .options(joinedload(EvidenceCandidate.document))
        .filter(
            EvidenceCandidate.patient_id == patient_id,
            EvidenceCandidate.requirement_id.in_(requirement_ids or [""]),
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
                support_candidate_ids=item.support_candidate_ids,
                insufficient_candidate_ids=item.insufficient_candidate_ids,
                contradiction_candidate_ids=item.contradiction_candidate_ids,
                support_candidates=[
                    by_id[candidate_id]
                    for candidate_id in item.support_candidate_ids
                    if candidate_id in by_id
                ],
                insufficient_candidates=[
                    by_id[candidate_id]
                    for candidate_id in item.insufficient_candidate_ids
                    if candidate_id in by_id
                ],
                contradiction_candidates=[
                    by_id[candidate_id]
                    for candidate_id in item.contradiction_candidate_ids
                    if candidate_id in by_id
                ],
                accepted_candidate_ids=item.support_candidate_ids,
                review_candidate_ids=item.insufficient_candidate_ids,
                rejected_candidate_ids=item.contradiction_candidate_ids,
                supporting_candidates=[
                    by_id[candidate_id]
                    for candidate_id in item.support_candidate_ids
                    if candidate_id in by_id
                ],
                review_candidates=[
                    by_id[candidate_id]
                    for candidate_id in item.insufficient_candidate_ids
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
    if not known_policy_id(policy_id):
        raise HTTPException(status_code=404, detail="Policy not found")
    evaluation = evaluate_patient_policy(
        db, patient_id, policy_id=policy_id, persist=True, force_nli=True
    )
    return _policy_evaluation_out(patient_id, evaluation, db)


@router.get("/{patient_id}/policy-evaluation", response_model=PolicyEvaluationOut)
def get_policy_evaluation(
    patient_id: str,
    policy_id: str = FICTIONAL_POLICY_ID,
    db: Session = Depends(get_db),
) -> PolicyEvaluationOut:
    """Return checklist using cached NLI scores when available (fast reload)."""
    document_service.ensure_patient(db, patient_id)
    if not known_policy_id(policy_id):
        raise HTTPException(status_code=404, detail="Policy not found")
    evaluation = evaluate_patient_policy(
        db, patient_id, policy_id=policy_id, persist=True, force_nli=False
    )
    return _policy_evaluation_out(patient_id, evaluation, db)


@router.get("/{patient_id}/evidence-packet", response_model=EvidencePacketOut)
def get_evidence_packet(
    patient_id: str,
    policy_id: str = FICTIONAL_POLICY_ID,
    db: Session = Depends(get_db),
) -> EvidencePacketOut:
    """Build the clinician review packet + missing-requirements checklist."""
    document_service.ensure_patient(db, patient_id)
    if not known_policy_id(policy_id):
        raise HTTPException(status_code=404, detail="Policy not found")
    # Reuse cached NLI; evaluation is passed so packet build does not re-score.
    evaluation = evaluate_patient_policy(
        db, patient_id, policy_id=policy_id, persist=True, force_nli=False
    )
    packet = build_evidence_packet(
        db, patient_id, policy_id=policy_id, evaluation=evaluation
    )
    return EvidencePacketOut(
        patient_id=packet.patient_id,
        policy_id=packet.policy_id,
        policy_name=packet.policy_name,
        disclaimer=packet.disclaimer,
        covered_requirement_ids=list(packet.covered_requirement_ids),
        selected_documents=[
            PacketDocumentOut(
                document_id=doc.document_id,
                source_label=doc.source_label,
                original_filename=doc.original_filename,
                document_type=doc.document_type,
                page_count=doc.page_count,
                covers_requirement_ids=list(doc.covers_requirement_ids),
                covers_requirement_titles=list(doc.covers_requirement_titles),
                strength_score=doc.strength_score,
            )
            for doc in packet.selected_documents
        ],
        omitted_document_ids=list(packet.omitted_document_ids),
        total_pages=packet.total_pages,
        packet_strength=packet.packet_strength,
        missing_evidence=[
            MissingEvidenceOut(
                requirement_id=item.requirement_id,
                title=item.title,
                status=item.status,
                explanation=item.explanation,
                suggested_document_types=list(item.suggested_document_types),
            )
            for item in packet.missing_evidence
        ],
        notes=list(packet.notes),
    )


@router.get("/{patient_id}/evidence-packet/export")
def export_evidence_packet(
    patient_id: str,
    policy_id: str = FICTIONAL_POLICY_ID,
    document_ids: str | None = None,
    db: Session = Depends(get_db),
) -> Response:
    """Download the PA evidence packet PDF (cover + attached source documents).

    Pass `document_ids` as a comma-separated list to use clinician selection
    instead of the auto-optimized packet.
    """
    document_service.ensure_patient(db, patient_id)
    if not known_policy_id(policy_id):
        raise HTTPException(status_code=404, detail="Policy not found")
    selected_ids = (
        [part.strip() for part in document_ids.split(",") if part.strip()]
        if document_ids is not None
        else None
    )
    try:
        pdf_bytes, filename = export_evidence_packet_pdf(
            db,
            patient_id,
            policy_id=policy_id,
            document_ids=selected_ids,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
        },
    )



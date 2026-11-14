from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.db import Observation, Patient
from app.models.schemas import (
    DocumentDetail,
    DocumentSummary,
    ObservationOut,
    PageText,
    PatientOut,
)
from app.services import documents as document_service

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


@router.get("/{patient_id}/observations", response_model=list[ObservationOut])
def list_observations(patient_id: str, db: Session = Depends(get_db)) -> list[Observation]:
    document_service.ensure_patient(db, patient_id)
    return (
        db.query(Observation)
        .filter(Observation.patient_id == patient_id)
        .order_by(Observation.created_at.desc())
        .all()
    )



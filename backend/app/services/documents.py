from __future__ import annotations

import shutil
import uuid
from pathlib import Path

from fastapi import HTTPException, UploadFile
from sqlalchemy.orm import Session, joinedload

from app.core.config import get_settings
from app.models.db import Document, DocumentPage, Patient
from app.services.pdf_extract import extract_pages

settings = get_settings()


def ensure_patient(db: Session, patient_id: str) -> Patient:
    patient = db.get(Patient, patient_id)
    if patient is None:
        raise HTTPException(status_code=404, detail=f"Patient not found: {patient_id}")
    return patient


def store_and_index_pdf(
    db: Session,
    *,
    patient_id: str,
    upload: UploadFile | None = None,
    source_path: Path | None = None,
    original_filename: str | None = None,
    document_type: str = "clinical_note",
    source_label: str | None = None,
    scenario_tag: str | None = None,
    document_id: str | None = None,
) -> Document:
    ensure_patient(db, patient_id)

    if upload is None and source_path is None:
        raise ValueError("Either upload or source_path is required")

    doc_id = document_id or str(uuid.uuid4())
    patient_dir = Path(settings.upload_dir) / patient_id
    patient_dir.mkdir(parents=True, exist_ok=True)

    name = original_filename or (upload.filename if upload else None) or (source_path.name if source_path else "document.pdf")
    safe_name = Path(name).name
    dest = patient_dir / f"{doc_id}_{safe_name}"

    if upload is not None:
        with dest.open("wb") as out:
            shutil.copyfileobj(upload.file, out)
    else:
        assert source_path is not None
        shutil.copy2(source_path, dest)

    pages = extract_pages(dest)

    document = Document(
        id=doc_id,
        patient_id=patient_id,
        filename=dest.name,
        original_filename=safe_name,
        document_type=document_type,
        storage_path=str(dest),
        page_count=len(pages),
        source_label=source_label or safe_name,
        scenario_tag=scenario_tag,
    )
    db.add(document)
    for page in pages:
        db.add(
            DocumentPage(
                document_id=doc_id,
                page_number=page["page_number"],
                text=page["text"],
            )
        )
    db.commit()
    db.refresh(document)
    return document


def list_documents(db: Session, patient_id: str) -> list[Document]:
    ensure_patient(db, patient_id)
    return (
        db.query(Document)
        .filter(Document.patient_id == patient_id)
        .order_by(Document.uploaded_at.desc())
        .all()
    )


def get_document(db: Session, patient_id: str, document_id: str) -> Document:
    ensure_patient(db, patient_id)
    document = (
        db.query(Document)
        .options(joinedload(Document.pages))
        .filter(Document.id == document_id, Document.patient_id == patient_id)
        .first()
    )
    if document is None:
        raise HTTPException(status_code=404, detail=f"Document not found: {document_id}")
    return document

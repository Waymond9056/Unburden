from pathlib import Path

import pymupdf
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base
from app.models.db import Document, DocumentPage, Patient
from app.services.evidence_retrieval import retrieve_for_document
from app.services.packet_export import export_evidence_packet_pdf
from app.services.pdf_extract import extract_pages
from app.services.seed import PATIENT_DOB, PATIENT_ID, PATIENT_NAME, generate_seed_pdfs


def _session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine, autocommit=False, autoflush=False)()


def test_export_attaches_selected_source_pdfs(tmp_path: Path) -> None:
    db = _session()
    db.add(Patient(id=PATIENT_ID, display_name=PATIENT_NAME, date_of_birth=PATIENT_DOB))
    db.commit()

    for spec in generate_seed_pdfs(tmp_path):
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

    pdf_bytes, filename = export_evidence_packet_pdf(db, PATIENT_ID)
    assert filename.endswith(".pdf")
    assert "Raymond" in filename or PATIENT_ID in filename
    assert pdf_bytes.startswith(b"%PDF")
    packet = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    # Cover, a divider, and the supporting medication-history PDF.
    assert packet.page_count >= 3
    text = "\n".join(page.get_text() for page in packet)
    assert "Pharmacy Medication History" in text

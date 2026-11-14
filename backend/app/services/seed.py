from __future__ import annotations

from datetime import date
from pathlib import Path

from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.db import Document, DocumentPage, EvidenceCandidate, Patient
from app.services.documents import store_and_index_pdf

settings = get_settings()

PATIENT_ID = settings.default_patient_id
PATIENT_NAME = "Raymond Yao"
PATIENT_DOB = date(1985, 3, 12)

JOHN_DOE_ID = "patient-john-doe"
JOHN_DOE_NAME = "John Doe"
JOHN_DOE_DOB = date(1978, 7, 4)

# Fictional disclaimer used on every generated page
DISCLAIMER = (
    "FICTIONAL SYNTHETIC RECORD — For Unburden hackathon demonstration only. "
    "Not a real patient. Not affiliated with any insurer or health system."
)


def _write_pdf(path: Path, title: str, paragraphs: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    styles = getSampleStyleSheet()
    story = [
        Paragraph(DISCLAIMER, styles["Normal"]),
        Spacer(1, 12),
        Paragraph(title, styles["Title"]),
        Spacer(1, 12),
        Paragraph(f"Patient: {PATIENT_NAME} (DOB {PATIENT_DOB.isoformat()})", styles["Normal"]),
        Spacer(1, 12),
    ]
    for text in paragraphs:
        story.append(Paragraph(text, styles["Normal"]))
        story.append(Spacer(1, 10))
    SimpleDocTemplate(str(path), pagesize=letter).build(story)


def generate_seed_pdfs(seed_dir: Path | None = None) -> list[dict]:
    """Create synthetic PDFs for demo scenarios A/B/C and return metadata."""
    root = Path(seed_dir or settings.seed_dir)
    root.mkdir(parents=True, exist_ok=True)

    specs = [
        {
            "filename": "pulmonary_consult_note.pdf",
            "document_type": "clinical_note",
            "source_label": "Pulmonary Consult Note — Riverside Specialty Clinic",
            "scenario_tag": "A,B,C",
            "title": "Pulmonary Consultation Note",
            "paragraphs": [
                "Date of service: 2025-09-18. Encounter type: outpatient pulmonology.",
                (
                    "Assessment: Severe persistent asthma, ICD-10 J45.50. Symptoms include "
                    "nocturnal awakenings and limited exercise tolerance despite adherence "
                    "to high-dose inhaled corticosteroid therapy."
                ),
                (
                    "Plan: Continue current controller regimen. Consider biologic therapy "
                    "pending prior authorization evidence packet review."
                ),
            ],
        },
        {
            "filename": "medication_history.pdf",
            "document_type": "medication_record",
            "source_label": "Pharmacy Medication History — Northlake Pharmacy",
            "scenario_tag": "A,B,C",
            "title": "Controller Medication History",
            "paragraphs": [
                "Report generated: 2025-10-02.",
                (
                    "Documented high-dose inhaled corticosteroid / long-acting beta agonist "
                    "trial: fluticasone-salmeterol 500/50 mcg twice daily from 2024-11-01 "
                    "through 2025-09-30 (greater than 3 months continuous therapy)."
                ),
                (
                    "Patient filled prescriptions monthly. Notes indicate inadequate symptom "
                    "control despite adherence. Oral prednisone burst prescribed 2025-06-12 "
                    "for acute exacerbation."
                ),
            ],
        },
        {
            "filename": "exacerbation_er_note.pdf",
            "document_type": "hospital_note",
            "source_label": "ED Visit Summary — Cedar Valley Medical Center",
            "scenario_tag": "A,B,C",
            "title": "Emergency Department Visit — Asthma Exacerbation",
            "paragraphs": [
                "Arrival date: 2025-06-12. Chief complaint: acute dyspnea and wheezing.",
                (
                    "Clinical course: Treated for severe asthma exacerbation with nebulized "
                    "bronchodilators and systemic corticosteroids. Discharged with oral "
                    "prednisone taper."
                ),
                (
                    "This visit counts as one documented exacerbation requiring systemic "
                    "corticosteroids within the prior 12 months."
                ),
            ],
        },
    ]

    created = []
    for spec in specs:
        path = root / spec["filename"]
        _write_pdf(path, spec["title"], spec["paragraphs"])
        created.append({**spec, "path": path})
    return created


def reset_patient_data(db: Session, patient_id: str = PATIENT_ID) -> None:
    """Remove existing documents/evidence candidates for a clean seed."""
    docs = db.query(Document).filter(Document.patient_id == patient_id).all()
    for doc in docs:
        path = Path(doc.storage_path)
        if path.exists():
            path.unlink()
        db.query(DocumentPage).filter(DocumentPage.document_id == doc.id).delete()
        db.query(EvidenceCandidate).filter(EvidenceCandidate.document_id == doc.id).delete()
        db.delete(doc)
    db.commit()


def ensure_patient_record(
    db: Session,
    *,
    patient_id: str,
    display_name: str,
    date_of_birth: date,
) -> Patient:
    patient = db.get(Patient, patient_id)
    if patient is None:
        patient = Patient(
            id=patient_id,
            display_name=display_name,
            date_of_birth=date_of_birth,
        )
        db.add(patient)
        db.commit()
        db.refresh(patient)
    return patient


def ensure_seed_patient(db: Session) -> Patient:
    return ensure_patient_record(
        db,
        patient_id=PATIENT_ID,
        display_name=PATIENT_NAME,
        date_of_birth=PATIENT_DOB,
    )


def ensure_demo_patients(db: Session) -> list[Patient]:
    """Ensure isolated demo charts exist (Raymond with seed docs; John empty)."""
    raymond = ensure_seed_patient(db)
    john = ensure_patient_record(
        db,
        patient_id=JOHN_DOE_ID,
        display_name=JOHN_DOE_NAME,
        date_of_birth=JOHN_DOE_DOB,
    )
    return [raymond, john]


def seed_database(db: Session, *, regenerate_pdfs: bool = True) -> list[str]:
    ensure_demo_patients(db)
    # Only resets Raymond Yao — John Doe's chart stays untouched.
    reset_patient_data(db, PATIENT_ID)

    specs = generate_seed_pdfs() if regenerate_pdfs else [
        {
            "filename": p.name,
            "path": p,
            "document_type": "",
            "source_label": p.stem,
            "scenario_tag": None,
        }
        for p in sorted(Path(settings.seed_dir).glob("*.pdf"))
    ]

    document_ids: list[str] = []
    for spec in specs:
        document = store_and_index_pdf(
            db,
            patient_id=PATIENT_ID,
            source_path=Path(spec["path"]),
            original_filename=spec["filename"],
            document_type=spec.get("document_type") or "",
            source_label=spec.get("source_label"),
            scenario_tag=spec.get("scenario_tag"),
        )
        document_ids.append(document.id)
    return document_ids

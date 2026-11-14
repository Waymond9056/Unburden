from __future__ import annotations

from datetime import date
from pathlib import Path

from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.db import Document, DocumentPage, Observation, Patient
from app.services.documents import store_and_index_pdf

settings = get_settings()

PATIENT_ID = settings.default_patient_id
PATIENT_NAME = "Raymond Yao"
PATIENT_DOB = date(1985, 3, 12)

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
        {
            "filename": "lab_eosinophils.pdf",
            "document_type": "laboratory_report",
            "source_label": "Laboratory Report — Absolute Blood Eosinophils",
            "scenario_tag": "A,C",
            "title": "Laboratory Report: Absolute Eosinophil Count",
            "paragraphs": [
                "Collection date: 2025-08-21. Specimen: whole blood.",
                (
                    "Absolute eosinophil count: 420 cells/µL (reference range 0–500). "
                    "Result qualifies under the fictional example policy threshold of "
                    "≥300 cells/µL within the prior 12 months."
                ),
                "Ordering clinician: Dr. Morgan Lee, Pulmonology.",
            ],
        },
        {
            "filename": "duplicate_consult_summary.pdf",
            "document_type": "clinical_note",
            "source_label": "Duplicate Consult Summary — overlapping content",
            "scenario_tag": "C",
            "title": "Visit Summary (Overlapping Content)",
            "paragraphs": [
                "Date: 2025-09-20. This note restates prior findings for Scenario C.",
                (
                    "Diagnosis reiterated: severe persistent asthma. Controller therapy "
                    "with fluticasone-salmeterol again documented. No new laboratory values."
                ),
                (
                    "Purpose: redundant documentation to test packet optimization and "
                    "avoid unnecessary document selection."
                ),
            ],
        },
        {
            "filename": "misleading_allergy_note.pdf",
            "document_type": "clinical_note",
            "source_label": "Allergy Clinic Note — nonqualifying similar language",
            "scenario_tag": "C",
            "title": "Allergy Clinic Note (Nonqualifying Evidence)",
            "paragraphs": [
                "Date of service: 2025-07-08.",
                (
                    "Patient has seasonal allergic rhinitis. Inhaled corticosteroid spray "
                    "for nasal symptoms was discussed. No systemic corticosteroid "
                    "exacerbation treatment occurred at this visit."
                ),
                (
                    "Eosinophils mentioned qualitatively as 'borderline elevated historically' "
                    "without a dated quantitative laboratory value. This note should not "
                    "alone establish the fictional lab requirement."
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
    """Remove existing documents/observations for a clean seed."""
    docs = db.query(Document).filter(Document.patient_id == patient_id).all()
    for doc in docs:
        path = Path(doc.storage_path)
        if path.exists():
            path.unlink()
        db.query(DocumentPage).filter(DocumentPage.document_id == doc.id).delete()
        db.query(Observation).filter(Observation.document_id == doc.id).delete()
        db.delete(doc)
    db.commit()


def ensure_seed_patient(db: Session) -> Patient:
    patient = db.get(Patient, PATIENT_ID)
    if patient is None:
        patient = Patient(
            id=PATIENT_ID,
            display_name=PATIENT_NAME,
            date_of_birth=PATIENT_DOB,
        )
        db.add(patient)
        db.commit()
        db.refresh(patient)
    return patient


def seed_database(db: Session, *, regenerate_pdfs: bool = True) -> list[str]:
    ensure_seed_patient(db)
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

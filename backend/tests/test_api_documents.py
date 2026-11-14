from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base, get_db
from app.main import app
from app.models.db import DocumentPage, EvidenceCandidate
from app.services.seed import PATIENT_ID, ensure_seed_patient, generate_seed_pdfs


engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
Base.metadata.create_all(bind=engine)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db
client = TestClient(app)


def test_upload_and_list_documents(tmp_path: Path) -> None:
    db = TestingSessionLocal()
    ensure_seed_patient(db)
    db.close()

    specs = generate_seed_pdfs(tmp_path)
    note = next(s for s in specs if s["filename"] == "pulmonary_consult_note.pdf")

    with note["path"].open("rb") as f:
        response = client.post(
            f"/api/patients/{PATIENT_ID}/documents",
            files={"file": ("pulmonary_consult_note.pdf", f, "application/pdf")},
            data={"document_type": "clinical_note", "source_label": "Consult note"},
        )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["page_count"] >= 1
    assert body["document_type"] == "clinical_note"

    listed = client.get(f"/api/patients/{PATIENT_ID}/documents")
    assert listed.status_code == 200
    assert any(d["id"] == body["id"] for d in listed.json())

    detail = client.get(f"/api/patients/{PATIENT_ID}/documents/{body['id']}")
    assert detail.status_code == 200
    pages = detail.json()["pages"]
    assert pages[0]["page_number"] == 1
    assert "asthma" in pages[0]["text"].lower()

    file_response = client.get(
        f"/api/patients/{PATIENT_ID}/documents/{body['id']}/file"
    )
    assert file_response.status_code == 200
    assert file_response.headers["content-type"].startswith("application/pdf")
    assert file_response.content[:4] == b"%PDF"

    candidates_response = client.get(f"/api/patients/{PATIENT_ID}/evidence-candidates")
    assert candidates_response.status_code == 200
    note_candidates = [
        item
        for item in candidates_response.json()
        if item["document_id"] == body["id"]
    ]
    assert {item["requirement_id"] for item in note_candidates} == {
        "documented_severe_asthma",
        "prior_controller_therapy",
    }

    db = TestingSessionLocal()
    for candidate in note_candidates:
        assert candidate["source_page"] == 1
        assert candidate["source_document_name"] == "Consult note"
        assert candidate["verification_status"] == "unverified_candidate"
        page = (
            db.query(DocumentPage)
            .filter(
                DocumentPage.document_id == body["id"],
                DocumentPage.page_number == candidate["source_page"],
            )
            .one()
        )
        stored = (
            db.query(EvidenceCandidate)
            .filter(EvidenceCandidate.id == candidate["id"])
            .one()
        )
        assert stored.supporting_quote in page.text
    db.close()

    filtered = client.get(
        f"/api/patients/{PATIENT_ID}/evidence-candidates",
        params={"requirement_id": "documented_severe_asthma"},
    )
    assert filtered.status_code == 200
    assert filtered.json()
    assert all(
        item["requirement_id"] == "documented_severe_asthma"
        for item in filtered.json()
    )


def test_upload_without_document_type_is_blank(tmp_path: Path) -> None:
    db = TestingSessionLocal()
    ensure_seed_patient(db)
    db.close()

    specs = generate_seed_pdfs(tmp_path)
    note = next(s for s in specs if s["filename"] == "pulmonary_consult_note.pdf")

    with note["path"].open("rb") as f:
        response = client.post(
            f"/api/patients/{PATIENT_ID}/documents",
            files={"file": ("pulmonary_consult_note.pdf", f, "application/pdf")},
        )

    assert response.status_code == 200, response.text
    assert response.json()["document_type"] == ""

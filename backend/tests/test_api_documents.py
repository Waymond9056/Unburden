from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base, get_db
from app.main import app
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
    lab = next(s for s in specs if s["filename"] == "lab_eosinophils.pdf")

    with lab["path"].open("rb") as f:
        response = client.post(
            f"/api/patients/{PATIENT_ID}/documents",
            files={"file": ("lab_eosinophils.pdf", f, "application/pdf")},
            data={"document_type": "laboratory_report", "source_label": "Lab EOS"},
        )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["page_count"] >= 1
    assert body["document_type"] == "laboratory_report"

    listed = client.get(f"/api/patients/{PATIENT_ID}/documents")
    assert listed.status_code == 200
    assert any(d["id"] == body["id"] for d in listed.json())

    detail = client.get(f"/api/patients/{PATIENT_ID}/documents/{body['id']}")
    assert detail.status_code == 200
    pages = detail.json()["pages"]
    assert pages[0]["page_number"] == 1
    assert "eosinophil" in pages[0]["text"].lower()

    file_response = client.get(
        f"/api/patients/{PATIENT_ID}/documents/{body['id']}/file"
    )
    assert file_response.status_code == 200
    assert file_response.headers["content-type"].startswith("application/pdf")
    assert file_response.content[:4] == b"%PDF"

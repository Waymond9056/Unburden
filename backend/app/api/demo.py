from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.models.schemas import SeedResponse
from app.services.seed import seed_database

router = APIRouter(prefix="/demo", tags=["demo"])
settings = get_settings()


@router.post("/seed", response_model=SeedResponse)
def seed_demo_data(db: Session = Depends(get_db)) -> SeedResponse:
    document_ids = seed_database(db, regenerate_pdfs=True)
    return SeedResponse(
        patient_id=settings.default_patient_id,
        documents_created=len(document_ids),
        document_ids=document_ids,
    )

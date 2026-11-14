from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.demo import router as demo_router
from app.api.patients import router as patients_router
from app.api.policies import router as policies_router
from app.core.config import get_settings
from app.core.database import SessionLocal, init_db
from app.models.schemas import HealthResponse
from app.services.seed import ensure_seed_patient, seed_database

settings = get_settings()


@asynccontextmanager
async def lifespan(_: FastAPI):
    Path(settings.upload_dir).mkdir(parents=True, exist_ok=True)
    Path(settings.seed_dir).mkdir(parents=True, exist_ok=True)
    db_path = settings.database_url.removeprefix("sqlite:///")
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    init_db()

    db = SessionLocal()
    try:
        ensure_seed_patient(db)
        # Auto-seed synthetic docs on first launch if the library is empty.
        from app.models.db import Document
        from app.services.evidence_retrieval import backfill_missing_candidates

        if db.query(Document).count() == 0:
            seed_database(db, regenerate_pdfs=True)
        else:
            # Upgrade Milestone 1 databases in place. Existing candidates and
            # future verification decisions are left untouched.
            backfill_missing_candidates(db)
    finally:
        db.close()

    yield


app = FastAPI(title=settings.app_name, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(patients_router, prefix=settings.api_prefix)
app.include_router(demo_router, prefix=settings.api_prefix)
app.include_router(policies_router, prefix=settings.api_prefix)


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok", app=settings.app_name)

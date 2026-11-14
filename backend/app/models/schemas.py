from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, Field


class PageText(BaseModel):
    page_number: int
    text: str


class DocumentSummary(BaseModel):
    id: str
    patient_id: str
    filename: str
    original_filename: str
    document_type: str
    page_count: int
    uploaded_at: datetime
    source_label: Optional[str] = None
    scenario_tag: Optional[str] = None


class DocumentDetail(DocumentSummary):
    pages: list[PageText] = Field(default_factory=list)


class PatientOut(BaseModel):
    id: str
    display_name: str
    date_of_birth: Optional[date] = None
    created_at: datetime


class ObservationOut(BaseModel):
    id: str
    patient_id: str
    document_id: str
    concept_type: str
    concept_code: Optional[str] = None
    value_text: Optional[str] = None
    value_numeric: Optional[float] = None
    value_units: Optional[str] = None
    event_date: Optional[date] = None
    interval_start: Optional[date] = None
    interval_end: Optional[date] = None
    source_page: int
    supporting_quote: str
    uncertainty: str
    review_status: str
    created_at: datetime


class HealthResponse(BaseModel):
    status: str
    app: str


class SeedResponse(BaseModel):
    patient_id: str
    documents_created: int
    document_ids: list[str]

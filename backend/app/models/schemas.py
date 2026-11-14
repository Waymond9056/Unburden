from datetime import date, datetime
from typing import Any, Optional

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


class PolicyRequirementOut(BaseModel):
    id: str
    policy_id: str
    title: str
    description: str


class EvidenceCandidateOut(BaseModel):
    id: str
    patient_id: str
    document_id: str
    policy_id: str
    requirement_id: str
    requirement_title: str
    source_page: int
    supporting_quote: str
    extracted_details: dict[str, Any] = Field(default_factory=dict)
    relevance_score: float
    retrieval_method: str
    verification_status: str
    created_at: datetime
    source_document_name: Optional[str] = None
    source_document_type: Optional[str] = None


class HealthResponse(BaseModel):
    status: str
    app: str


class SeedResponse(BaseModel):
    patient_id: str
    documents_created: int
    document_ids: list[str]

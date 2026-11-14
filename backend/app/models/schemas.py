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


class PolicyOut(BaseModel):
    id: str
    name: str
    disclaimer: str
    logic: str
    as_of_date: date
    requirements: list[PolicyRequirementOut]


class CandidateVerdictOut(BaseModel):
    candidate_id: str
    status: str
    reasons: list[str] = Field(default_factory=list)


class RequirementEvaluationOut(BaseModel):
    requirement_id: str
    title: str
    status: str
    explanation: str
    suggested_document_types: list[str] = Field(default_factory=list)
    accepted_candidate_ids: list[str] = Field(default_factory=list)
    review_candidate_ids: list[str] = Field(default_factory=list)
    rejected_candidate_ids: list[str] = Field(default_factory=list)
    supporting_candidates: list[EvidenceCandidateOut] = Field(default_factory=list)
    review_candidates: list[EvidenceCandidateOut] = Field(default_factory=list)


class PolicyEvaluationOut(BaseModel):
    patient_id: str
    policy_id: str
    policy_name: str
    disclaimer: str
    as_of_date: date
    logic: str
    overall_status: str
    requirements: list[RequirementEvaluationOut]
    candidate_verdicts: list[CandidateVerdictOut] = Field(default_factory=list)


class HealthResponse(BaseModel):
    status: str
    app: str


class SeedResponse(BaseModel):
    patient_id: str
    documents_created: int
    document_ids: list[str]

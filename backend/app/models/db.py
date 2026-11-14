from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from sqlalchemy import Date, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Patient(Base):
    __tablename__ = "patients"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    date_of_birth: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    documents: Mapped[list[Document]] = relationship(back_populates="patient", cascade="all, delete-orphan")
    evidence_candidates: Mapped[list[EvidenceCandidate]] = relationship(
        back_populates="patient", cascade="all, delete-orphan"
    )


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    patient_id: Mapped[str] = mapped_column(ForeignKey("patients.id", ondelete="CASCADE"), index=True)
    filename: Mapped[str] = mapped_column(String(512), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(512), nullable=False)
    document_type: Mapped[str] = mapped_column(String(128), default="")
    storage_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    page_count: Mapped[int] = mapped_column(Integer, default=0)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    source_label: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    scenario_tag: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    patient: Mapped[Patient] = relationship(back_populates="documents")
    pages: Mapped[list[DocumentPage]] = relationship(
        back_populates="document", cascade="all, delete-orphan", order_by="DocumentPage.page_number"
    )
    evidence_candidates: Mapped[list[EvidenceCandidate]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )


class DocumentPage(Base):
    __tablename__ = "document_pages"
    __table_args__ = (UniqueConstraint("document_id", "page_number", name="uq_document_page"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), index=True)
    page_number: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, default="")

    document: Mapped[Document] = relationship(back_populates="pages")


class EvidenceCandidate(Base):
    """An exact source passage retrieved for one policy requirement."""

    __tablename__ = "evidence_candidates"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    patient_id: Mapped[str] = mapped_column(ForeignKey("patients.id", ondelete="CASCADE"), index=True)
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), index=True)
    policy_id: Mapped[str] = mapped_column(String(128), index=True)
    requirement_id: Mapped[str] = mapped_column(String(128), index=True)
    source_page: Mapped[int] = mapped_column(Integer, nullable=False)
    supporting_quote: Mapped[str] = mapped_column(Text, nullable=False)
    extracted_details_json: Mapped[str] = mapped_column(Text, default="{}")
    relevance_score: Mapped[float] = mapped_column(Float, default=0.0)
    retrieval_method: Mapped[str] = mapped_column(String(64), default="lexical")
    verification_status: Mapped[str] = mapped_column(String(64), default="unverified_candidate")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    patient: Mapped[Patient] = relationship(back_populates="evidence_candidates")
    document: Mapped[Document] = relationship(back_populates="evidence_candidates")

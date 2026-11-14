from __future__ import annotations

import json
import re
import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.models.db import Document, DocumentPage, EvidenceCandidate
from app.services.policy import FICTIONAL_POLICY_ID, REQUIREMENTS, RequirementDefinition

DATE_PATTERN = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")
NUMBER_WITH_UNITS_PATTERN = re.compile(
    r"\b\d+(?:\.\d+)?(?:/\d+(?:\.\d+)?)?\s*(?:mcg|mg|cells/(?:µL|uL))\b",
    flags=re.IGNORECASE,
)


def _page_passages(page_text: str) -> list[tuple[int, int, str]]:
    """Return exact sentence spans so adjacent context remains a source substring."""
    separators = list(re.finditer(r"(?<=[.!?])\s+(?=[A-Z])", page_text))
    ranges: list[tuple[int, int, str]] = []
    start = 0
    for separator in separators:
        raw = page_text[start : separator.start()]
        stripped = raw.strip()
        if stripped:
            offset = raw.index(stripped)
            ranges.append((start + offset, start + offset + len(stripped), stripped))
        start = separator.end()
    raw = page_text[start:]
    stripped = raw.strip()
    if stripped:
        offset = raw.index(stripped)
        ranges.append((start + offset, start + offset + len(stripped), stripped))
    return ranges


def _matched_terms(passage: str, requirement: RequirementDefinition) -> list[str]:
    passage_lower = passage.lower()
    return [term for term in requirement.retrieval_terms if term.lower() in passage_lower]


def _extract_needed_details(
    passage: str,
    requirement: RequirementDefinition,
    matched_terms: list[str],
) -> dict[str, Any]:
    details: dict[str, Any] = {}
    if "dates" in requirement.detail_fields:
        dates = list(dict.fromkeys(DATE_PATTERN.findall(passage)))
        if dates:
            details["dates"] = dates
    if "dose_mentions" in requirement.detail_fields:
        doses = list(dict.fromkeys(NUMBER_WITH_UNITS_PATTERN.findall(passage)))
        if doses:
            details["dose_mentions"] = doses
    if "numeric_mentions" in requirement.detail_fields:
        values = list(dict.fromkeys(NUMBER_WITH_UNITS_PATTERN.findall(passage)))
        if values:
            details["numeric_mentions"] = values
    details["matched_terms"] = matched_terms
    return details


def retrieve_page_candidates(
    *,
    document: Document,
    page: DocumentPage,
    requirement: RequirementDefinition,
) -> list[EvidenceCandidate]:
    matches: list[tuple[int, int, str, list[str]]] = []
    passages = _page_passages(page.text)
    for index, (start, end, passage) in enumerate(passages):
        terms = _matched_terms(passage, requirement)
        if terms:
            matches.append((index, start, end, terms))
    if not matches:
        return []

    index, start, end, terms = max(matches, key=lambda item: len(item[3]))
    # Walk backward a few sentences so nearby dates stay attached to the citation.
    cursor = index
    while cursor > 0 and not DATE_PATTERN.search(page.text[start:end]):
        previous_start, _, previous = passages[cursor - 1]
        if DATE_PATTERN.search(previous) or cursor == index:
            start = previous_start
            cursor -= 1
            if DATE_PATTERN.search(page.text[start:end]):
                break
            continue
        break
    passage = page.text[start:end]
    score = min(1.0, 0.35 + (0.2 * len(terms)))
    return [
        EvidenceCandidate(
            id=str(uuid.uuid4()),
            patient_id=document.patient_id,
            document_id=document.id,
            policy_id=requirement.policy_id,
            requirement_id=requirement.id,
            source_page=page.page_number,
            supporting_quote=passage,
            extracted_details_json=json.dumps(
                _extract_needed_details(passage, requirement, terms),
                ensure_ascii=False,
            ),
            relevance_score=score,
            retrieval_method="lexical",
            verification_status="unverified_candidate",
        )
    ]


def retrieve_for_document(db: Session, document: Document) -> list[EvidenceCandidate]:
    pages = (
        db.query(DocumentPage)
        .filter(DocumentPage.document_id == document.id)
        .order_by(DocumentPage.page_number)
        .all()
    )
    db.query(EvidenceCandidate).filter(
        EvidenceCandidate.document_id == document.id,
        EvidenceCandidate.policy_id == FICTIONAL_POLICY_ID,
    ).delete()

    candidates = [
        candidate
        for page in pages
        for requirement in REQUIREMENTS
        for candidate in retrieve_page_candidates(
            document=document,
            page=page,
            requirement=requirement,
        )
    ]
    db.add_all(candidates)
    db.commit()
    for candidate in candidates:
        db.refresh(candidate)
    return candidates


def retrieve_for_patient(db: Session, patient_id: str) -> list[EvidenceCandidate]:
    candidates: list[EvidenceCandidate] = []
    documents = db.query(Document).filter(Document.patient_id == patient_id).all()
    for document in documents:
        candidates.extend(retrieve_for_document(db, document))
    return candidates


def backfill_missing_candidates(db: Session) -> int:
    """Index pre-Milestone-2 documents without touching existing candidates."""
    created = 0
    for document in db.query(Document).all():
        existing = (
            db.query(EvidenceCandidate)
            .filter(
                EvidenceCandidate.document_id == document.id,
                EvidenceCandidate.policy_id == FICTIONAL_POLICY_ID,
            )
            .count()
        )
        if existing == 0:
            created += len(retrieve_for_document(db, document))
    return created

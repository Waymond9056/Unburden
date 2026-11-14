"""Milestone 4: choose what to send, and what is still missing.

Milestone 3 decides what we can prove. This module builds the clinician-facing
deliverable: a concise packet of verified sources, plus a missing-requirements
checklist. Size is only a tie-breaker after evidence strength / source fit.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations

from sqlalchemy.orm import Session, joinedload

from app.models.db import Document, EvidenceCandidate
from app.services.evidence_verification import (
    CANDIDATE_ACCEPTED,
    STATUS_NEEDS_REVIEW,
    STATUS_NOT_ESTABLISHED,
    STATUS_SUPPORTED,
    PolicyEvaluation,
    evaluate_patient_policy,
)
from app.services.policy import FICTIONAL_POLICY_ID, REQUIREMENTS_BY_ID, RequirementDefinition

# Source-reliability prior by document type. Used only after verification accepts
# a candidate — never to override Milestone 3 correctness.
_TYPE_RELIABILITY = {
    "laboratory_report": 3.0,
    "medication_record": 3.0,
    "hospital_note": 2.5,
    "clinical_note": 1.5,
}


@dataclass(frozen=True)
class PacketDocument:
    document_id: str
    source_label: str
    original_filename: str
    document_type: str
    page_count: int
    covers_requirement_ids: tuple[str, ...]
    covers_requirement_titles: tuple[str, ...]
    strength_score: float


@dataclass(frozen=True)
class MissingEvidenceItem:
    requirement_id: str
    title: str
    status: str
    explanation: str
    suggested_document_types: tuple[str, ...]


@dataclass(frozen=True)
class EvidencePacket:
    patient_id: str
    policy_id: str
    policy_name: str
    disclaimer: str
    covered_requirement_ids: tuple[str, ...]
    selected_documents: tuple[PacketDocument, ...]
    omitted_document_ids: tuple[str, ...]
    total_pages: int
    packet_strength: float
    missing_evidence: tuple[MissingEvidenceItem, ...]
    notes: tuple[str, ...]


@dataclass(frozen=True)
class _Edge:
    """Verified document → requirement mapping with strength."""

    document_id: str
    requirement_id: str
    strength: float
    relevance_score: float


def _type_reliability(document_type: str) -> float:
    return _TYPE_RELIABILITY.get((document_type or "").strip(), 1.0)


def _requirement_type_fit(requirement: RequirementDefinition, document_type: str) -> float:
    """Prefer insurer-acceptable documentation types listed earlier in the policy."""
    doc_type = (document_type or "").strip()
    allowed = requirement.acceptable_document_types
    if not allowed:
        return 1.0
    if doc_type not in allowed:
        return 0.25
    # Earlier entries are treated as stronger / more preferred sources.
    index = allowed.index(doc_type)
    return 1.0 + (len(allowed) - index) * 0.35


def _edge_strength(
    *,
    requirement: RequirementDefinition,
    document: Document,
    relevance_score: float,
) -> float:
    return (
        _type_reliability(document.document_type)
        * _requirement_type_fit(requirement, document.document_type)
        * (0.5 + max(relevance_score, 0.0))
    )


def _missing_explanation(requirement_id: str, status: str) -> str:
    requirement = REQUIREMENTS_BY_ID[requirement_id]
    if status == STATUS_NOT_ESTABLISHED:
        return (
            f"{requirement.title} is required by this example policy, but no qualifying "
            "source-backed evidence was established in the uploaded documents. "
            "This does not mean the patient clinically fails the criterion."
        )
    return (
        f"{requirement.title} has candidate material that still needs clinician review "
        "before it can be treated as established for the packet."
    )


def _verified_edges(
    db: Session,
    patient_id: str,
    evaluation: PolicyEvaluation,
) -> list[_Edge]:
    supported_ids = {
        item.requirement_id
        for item in evaluation.requirements
        if item.status == STATUS_SUPPORTED
    }
    accepted_ids = {
        candidate_id
        for item in evaluation.requirements
        if item.status == STATUS_SUPPORTED
        for candidate_id in item.accepted_candidate_ids
    }
    if not supported_ids or not accepted_ids:
        return []

    candidates = (
        db.query(EvidenceCandidate)
        .options(joinedload(EvidenceCandidate.document))
        .filter(
            EvidenceCandidate.patient_id == patient_id,
            EvidenceCandidate.policy_id == evaluation.policy_id,
            EvidenceCandidate.id.in_(accepted_ids),
        )
        .all()
    )

    edges: list[_Edge] = []
    for candidate in candidates:
        if candidate.verification_status != CANDIDATE_ACCEPTED:
            continue
        if candidate.requirement_id not in supported_ids:
            continue
        requirement = REQUIREMENTS_BY_ID[candidate.requirement_id]
        document = candidate.document
        edges.append(
            _Edge(
                document_id=candidate.document_id,
                requirement_id=candidate.requirement_id,
                strength=_edge_strength(
                    requirement=requirement,
                    document=document,
                    relevance_score=candidate.relevance_score,
                ),
                relevance_score=candidate.relevance_score,
            )
        )
    return edges


def _best_strength_for_requirement(
    selected: set[str],
    requirement_id: str,
    edges: list[_Edge],
) -> float:
    scores = [
        edge.strength
        for edge in edges
        if edge.requirement_id == requirement_id and edge.document_id in selected
    ]
    return max(scores) if scores else 0.0


def _packet_cost(
    selected: tuple[str, ...],
    *,
    required: set[str],
    coverage: dict[str, set[str]],
    documents: dict[str, Document],
    edges: list[_Edge],
) -> tuple[float, int, int] | None:
    covered: set[str] = set()
    for doc_id in selected:
        covered |= coverage.get(doc_id, set())
    if not required.issubset(covered):
        return None

    # Strength first (negated so lower tuple is better), then size proxies.
    strength = sum(
        _best_strength_for_requirement(set(selected), req_id, edges) for req_id in required
    )
    pages = sum(documents[doc_id].page_count for doc_id in selected)
    return (-strength, len(selected), pages)


def _exact_best_packet(
    *,
    required: set[str],
    coverage: dict[str, set[str]],
    documents: dict[str, Document],
    edges: list[_Edge],
) -> list[str]:
    """Exact search over document subsets for small corpora.

    Objective (in order):
    1. Cover every Milestone-3 SUPPORTED requirement
    2. Maximize evidence strength / source fit
    3. Minimize document count, then page count
    """
    doc_ids = [doc_id for doc_id, reqs in coverage.items() if reqs & required]
    if not doc_ids or not required:
        return []

    best: list[str] | None = None
    best_cost: tuple[float, int, int] | None = None

    for size in range(1, len(doc_ids) + 1):
        for combo in combinations(sorted(doc_ids), size):
            cost = _packet_cost(
                combo,
                required=required,
                coverage=coverage,
                documents=documents,
                edges=edges,
            )
            if cost is None:
                continue
            if best_cost is None or cost < best_cost:
                best_cost = cost
                best = list(combo)

    return best or []


def build_evidence_packet(
    db: Session,
    patient_id: str,
    *,
    policy_id: str = FICTIONAL_POLICY_ID,
    evaluation: PolicyEvaluation | None = None,
) -> EvidencePacket:
    evaluation = evaluation or evaluate_patient_policy(
        db, patient_id, policy_id=policy_id, persist=True
    )

    supported = {
        item.requirement_id
        for item in evaluation.requirements
        if item.status == STATUS_SUPPORTED
    }
    edges = _verified_edges(db, patient_id, evaluation)
    coverage: dict[str, set[str]] = {}
    for edge in edges:
        coverage.setdefault(edge.document_id, set()).add(edge.requirement_id)

    documents = {
        doc.id: doc
        for doc in db.query(Document).filter(Document.patient_id == patient_id).all()
    }

    # Hackathon corpora stay small; exact search is intentional and preferred.
    selected_ids = _exact_best_packet(
        required=supported,
        coverage=coverage,
        documents=documents,
        edges=edges,
    )

    selected_docs: list[PacketDocument] = []
    covered_by_packet: set[str] = set()
    for doc_id in selected_ids:
        req_ids = tuple(sorted(coverage.get(doc_id, set()) & supported))
        covered_by_packet.update(req_ids)
        doc = documents[doc_id]
        doc_strength = sum(
            edge.strength
            for edge in edges
            if edge.document_id == doc_id and edge.requirement_id in req_ids
        )
        selected_docs.append(
            PacketDocument(
                document_id=doc.id,
                source_label=doc.source_label or doc.original_filename,
                original_filename=doc.original_filename,
                document_type=doc.document_type,
                page_count=doc.page_count,
                covers_requirement_ids=req_ids,
                covers_requirement_titles=tuple(
                    REQUIREMENTS_BY_ID[req_id].title for req_id in req_ids
                ),
                strength_score=round(doc_strength, 3),
            )
        )

    # Stable clinician-facing order: stronger packet members first.
    selected_docs.sort(key=lambda item: (-item.strength_score, item.source_label))

    omitted = tuple(sorted(doc_id for doc_id in coverage if doc_id not in selected_ids))

    missing: list[MissingEvidenceItem] = []
    for item in evaluation.requirements:
        if item.status == STATUS_NOT_ESTABLISHED:
            missing.append(
                MissingEvidenceItem(
                    requirement_id=item.requirement_id,
                    title=item.title,
                    status=item.status,
                    explanation=_missing_explanation(item.requirement_id, item.status),
                    suggested_document_types=tuple(item.suggested_document_types),
                )
            )
        elif item.status == STATUS_NEEDS_REVIEW and not item.accepted_candidate_ids:
            missing.append(
                MissingEvidenceItem(
                    requirement_id=item.requirement_id,
                    title=item.title,
                    status=item.status,
                    explanation=_missing_explanation(item.requirement_id, item.status),
                    suggested_document_types=tuple(item.suggested_document_types),
                )
            )

    packet_strength = sum(
        _best_strength_for_requirement(set(selected_ids), req_id, edges)
        for req_id in supported
    )

    notes = [
        "Packet includes only Milestone-3 accepted, source-verified evidence.",
        "Selection maximizes evidence strength and source fit; page/document count is a secondary tie-breaker.",
        "This is a review packet for a clinician — not an insurer submission and not coverage approval.",
        evaluation.disclaimer,
    ]
    if omitted:
        notes.append(
            f"Omitted {len(omitted)} document(s) that were redundant or weaker for covered requirements."
        )

    return EvidencePacket(
        patient_id=patient_id,
        policy_id=evaluation.policy_id,
        policy_name=evaluation.policy_name,
        disclaimer=evaluation.disclaimer,
        covered_requirement_ids=tuple(sorted(covered_by_packet)),
        selected_documents=tuple(selected_docs),
        omitted_document_ids=omitted,
        total_pages=sum(doc.page_count for doc in selected_docs),
        packet_strength=round(packet_strength, 3),
        missing_evidence=tuple(missing),
        notes=tuple(notes),
    )

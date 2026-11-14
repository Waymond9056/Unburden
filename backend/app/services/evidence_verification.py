from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

from sqlalchemy.orm import Session, joinedload

from app.core.config import get_settings
from app.models.db import DocumentPage, EvidenceCandidate
from app.services.policy import (
    FICTIONAL_POLICY_ID,
    PolicyDefinition,
    RequirementDefinition,
    load_policy,
)
from app.services.value_parsing import (
    extract_dates_from_text,
    find_numeric_mentions,
    parse_date_token,
    select_threshold_values,
)

STATUS_SUPPORTED = "SUPPORTED"
STATUS_NOT_ESTABLISHED = "NOT_ESTABLISHED"
STATUS_NEEDS_REVIEW = "NEEDS_REVIEW"

CANDIDATE_ACCEPTED = "accepted"
CANDIDATE_REJECTED = "rejected"
CANDIDATE_NEEDS_REVIEW = "needs_review"


@dataclass
class CandidateVerdict:
    candidate_id: str
    status: str
    reasons: list[str]


@dataclass
class RequirementEvaluation:
    requirement_id: str
    title: str
    status: str
    explanation: str
    suggested_document_types: list[str]
    accepted_candidate_ids: list[str]
    review_candidate_ids: list[str]
    rejected_candidate_ids: list[str]


@dataclass
class PolicyEvaluation:
    policy_id: str
    policy_name: str
    disclaimer: str
    as_of_date: date
    logic: str
    overall_status: str
    requirements: list[RequirementEvaluation]
    candidate_verdicts: list[CandidateVerdict]


def _parse_details(candidate: EvidenceCandidate) -> dict[str, Any]:
    try:
        data = json.loads(candidate.extracted_details_json or "{}")
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _quote_in_source(db: Session, candidate: EvidenceCandidate) -> bool:
    page = (
        db.query(DocumentPage)
        .filter(
            DocumentPage.document_id == candidate.document_id,
            DocumentPage.page_number == candidate.source_page,
        )
        .first()
    )
    if page is None:
        return False
    return candidate.supporting_quote in (page.text or "")


def _contains_any(text: str, needles: tuple[str, ...]) -> bool:
    lowered = text.lower()
    return any(needle.lower() in lowered for needle in needles)


def _extract_dates(candidate: EvidenceCandidate, details: dict[str, Any]) -> list[date]:
    parsed: list[date] = []
    seen: set[date] = set()

    raw_dates = details.get("dates")
    if isinstance(raw_dates, list):
        for item in raw_dates:
            value = parse_date_token(str(item))
            if value is not None and value not in seen:
                seen.add(value)
                parsed.append(value)

    for value in extract_dates_from_text(candidate.supporting_quote or ""):
        if value not in seen:
            seen.add(value)
            parsed.append(value)
    return parsed


def _months_ago(as_of: date, months: int) -> date:
    year = as_of.year
    month = as_of.month - months
    while month <= 0:
        month += 12
        year -= 1
    day = min(
        as_of.day,
        [
            31,
            29 if year % 4 == 0 and (year % 100 != 0 or year % 400 == 0) else 28,
            31,
            30,
            31,
            30,
            31,
            31,
            30,
            31,
            30,
            31,
        ][month - 1],
    )
    return date(year, month, day)


def _numeric_decision(
    candidate: EvidenceCandidate,
    details: dict[str, Any],
    unit_substring: str,
) -> tuple[list[float], bool, str | None]:
    """Collect threshold candidates; approximate-only evidence needs review."""
    mentions = list(find_numeric_mentions(candidate.supporting_quote or ""))
    raw_mentions = details.get("numeric_mentions")
    if isinstance(raw_mentions, list):
        for item in raw_mentions:
            mentions.extend(find_numeric_mentions(str(item)))
    return select_threshold_values(mentions, unit_substring)


def _interval_days(dates: list[date]) -> int | None:
    if len(dates) < 2:
        return None
    return (max(dates) - min(dates)).days


def _nli_enabled(use_nli: bool | None) -> bool:
    if use_nli is not None:
        return use_nli
    return bool(get_settings().use_nli_support)


def _apply_nli_signal(
    quote: str,
    requirement: RequirementDefinition,
) -> CandidateVerdict | str | None:
    """Optional DeBERTa negation / support-note signal.

    Returns:
      - CandidateVerdict for reject/review short-circuit
      - str support note to append if math later accepts
      - None if NLI is unavailable or has no action
    Never performs date/numeric comparisons.
    """
    from app.services.nli_deberta import (
        NliDependenciesMissing,
        interpret_nli_verification_signal,
        ml_dependencies_available,
        score_requirement_passage,
    )

    if not ml_dependencies_available():
        return None
    settings = get_settings()
    model_name = (settings.nli_model_name or "").strip() or None
    try:
        score = (
            score_requirement_passage(quote, requirement, model_name=model_name)
            if model_name
            else score_requirement_passage(quote, requirement)
        )
    except NliDependenciesMissing:
        return None
    # Thresholds: env > TREC-calibrated file > config defaults.
    signal = interpret_nli_verification_signal(score)
    if signal.action == "reject":
        return CandidateVerdict(
            candidate_id="",  # filled by caller
            status=CANDIDATE_REJECTED,
            reasons=[signal.reason],
        )
    if signal.action == "review":
        return CandidateVerdict(
            candidate_id="",
            status=CANDIDATE_NEEDS_REVIEW,
            reasons=[signal.reason],
        )
    if signal.action == "support_note":
        return signal.reason
    return None


def verify_candidate(
    db: Session,
    candidate: EvidenceCandidate,
    requirement: RequirementDefinition,
    *,
    as_of_date: date,
    use_nli: bool | None = None,
) -> CandidateVerdict:
    reasons: list[str] = []
    quote = candidate.supporting_quote or ""
    details = _parse_details(candidate)
    doc_type = (candidate.document.document_type or "").strip()

    if not _quote_in_source(db, candidate):
        return CandidateVerdict(
            candidate_id=candidate.id,
            status=CANDIDATE_REJECTED,
            reasons=["Supporting quotation was not found in the source page text."],
        )

    if requirement.acceptable_document_types:
        if not doc_type:
            return CandidateVerdict(
                candidate_id=candidate.id,
                status=CANDIDATE_NEEDS_REVIEW,
                reasons=["Document type is missing; cannot confirm acceptable documentation type."],
            )
        if doc_type not in requirement.acceptable_document_types:
            return CandidateVerdict(
                candidate_id=candidate.id,
                status=CANDIDATE_REJECTED,
                reasons=[
                    f"Document type '{doc_type}' is not acceptable for this requirement "
                    f"(allowed: {', '.join(requirement.acceptable_document_types)})."
                ],
            )

    if requirement.reject_if_quote_matches_any and _contains_any(
        quote, requirement.reject_if_quote_matches_any
    ):
        return CandidateVerdict(
            candidate_id=candidate.id,
            status=CANDIDATE_REJECTED,
            reasons=["Passage contains language that disqualifies it under policy constraints."],
        )

    if requirement.ambiguous_if_quote_matches_any and _contains_any(
        quote, requirement.ambiguous_if_quote_matches_any
    ):
        return CandidateVerdict(
            candidate_id=candidate.id,
            status=CANDIDATE_NEEDS_REVIEW,
            reasons=["Passage is ambiguous or non-quantitative relative to the requirement."],
        )

    if requirement.must_match_any and not _contains_any(quote, requirement.must_match_any):
        return CandidateVerdict(
            candidate_id=candidate.id,
            status=CANDIDATE_REJECTED,
            reasons=["Passage does not contain a required clinical concept for this requirement."],
        )

    # DeBERTa precision/negation signal: only after on-topic keyword gate.
    # Date/numeric/doc-type math below remains the source of truth for thresholds.
    nli_support_note: str | None = None
    if _nli_enabled(use_nli):
        nli_result = _apply_nli_signal(quote, requirement)
        if isinstance(nli_result, CandidateVerdict):
            return CandidateVerdict(
                candidate_id=candidate.id,
                status=nli_result.status,
                reasons=nli_result.reasons,
            )
        if isinstance(nli_result, str) and nli_result:
            nli_support_note = nli_result

    dates = _extract_dates(candidate, details)
    if requirement.temporal is not None:
        if requirement.temporal.date_required and not dates:
            return CandidateVerdict(
                candidate_id=candidate.id,
                status=CANDIDATE_NEEDS_REVIEW,
                reasons=["A dated event is required, but no usable date was found in the passage."],
            )
        if dates:
            earliest_allowed = _months_ago(as_of_date, requirement.temporal.within_months)
            if max(dates) < earliest_allowed:
                return CandidateVerdict(
                    candidate_id=candidate.id,
                    status=CANDIDATE_REJECTED,
                    reasons=[
                        f"Event date falls outside the required {requirement.temporal.within_months}-month window "
                        f"(as of {as_of_date.isoformat()})."
                    ],
                )
            if max(dates) > as_of_date + timedelta(days=1):
                return CandidateVerdict(
                    candidate_id=candidate.id,
                    status=CANDIDATE_NEEDS_REVIEW,
                    reasons=["Event date is after the policy as-of date and needs clinician review."],
                )

    if requirement.require_interval_days_min is not None:
        span = _interval_days(dates)
        if span is None:
            # Single-date therapy mention without an interval → review, not auto-accept.
            return CandidateVerdict(
                candidate_id=candidate.id,
                status=CANDIDATE_NEEDS_REVIEW,
                reasons=[
                    "Controller duration could not be confirmed from dated interval evidence in this passage."
                ],
            )
        if span < requirement.require_interval_days_min:
            return CandidateVerdict(
                candidate_id=candidate.id,
                status=CANDIDATE_REJECTED,
                reasons=[
                    f"Documented therapy interval ({span} days) is shorter than the required "
                    f"{requirement.require_interval_days_min} days."
                ],
            )

    if requirement.numeric is not None:
        values, approximate_only, review_reason = _numeric_decision(
            candidate, details, requirement.numeric.unit_substring
        )
        if not values:
            return CandidateVerdict(
                candidate_id=candidate.id,
                status=CANDIDATE_NEEDS_REVIEW,
                reasons=["No quantitative value with acceptable units was found."],
            )
        if approximate_only:
            return CandidateVerdict(
                candidate_id=candidate.id,
                status=CANDIDATE_NEEDS_REVIEW,
                reasons=[review_reason or "Approximate numeric language needs clinician review."],
            )
        if max(values) < requirement.numeric.min_value:
            return CandidateVerdict(
                candidate_id=candidate.id,
                status=CANDIDATE_REJECTED,
                reasons=[
                    f"Numeric value {max(values)} does not meet the minimum "
                    f"{requirement.numeric.min_value}."
                ],
            )

    reasons.append("Candidate satisfies structured policy constraints and source citation checks.")
    if nli_support_note:
        reasons.append(nli_support_note)
    return CandidateVerdict(
        candidate_id=candidate.id,
        status=CANDIDATE_ACCEPTED,
        reasons=reasons,
    )


def _requirement_status(
    requirement: RequirementDefinition,
    verdicts: list[CandidateVerdict],
) -> RequirementEvaluation:
    accepted = [v for v in verdicts if v.status == CANDIDATE_ACCEPTED]
    reviews = [v for v in verdicts if v.status == CANDIDATE_NEEDS_REVIEW]
    rejected = [v for v in verdicts if v.status == CANDIDATE_REJECTED]

    if len(accepted) >= requirement.min_accepted_candidates:
        status = STATUS_SUPPORTED
        explanation = (
            f"Found {len(accepted)} accepted source-backed candidate(s) meeting policy constraints."
        )
    elif reviews:
        status = STATUS_NEEDS_REVIEW
        explanation = (
            "No candidate fully established the requirement; at least one passage needs clinician review."
        )
    else:
        status = STATUS_NOT_ESTABLISHED
        explanation = (
            "Available records do not establish this documentation requirement under the configured rules. "
            "This does not mean the patient clinically fails the criterion."
        )

    return RequirementEvaluation(
        requirement_id=requirement.id,
        title=requirement.title,
        status=status,
        explanation=explanation,
        suggested_document_types=list(requirement.suggested_document_types),
        accepted_candidate_ids=[v.candidate_id for v in accepted],
        review_candidate_ids=[v.candidate_id for v in reviews],
        rejected_candidate_ids=[v.candidate_id for v in rejected],
    )


def _overall_status(logic: str, requirement_evals: list[RequirementEvaluation]) -> str:
    statuses = [item.status for item in requirement_evals]
    if logic.upper() == "OR":
        if STATUS_SUPPORTED in statuses:
            return STATUS_SUPPORTED
        if STATUS_NEEDS_REVIEW in statuses:
            return STATUS_NEEDS_REVIEW
        return STATUS_NOT_ESTABLISHED

    # Default AND
    if all(status == STATUS_SUPPORTED for status in statuses):
        return STATUS_SUPPORTED
    if any(status == STATUS_NEEDS_REVIEW for status in statuses):
        return STATUS_NEEDS_REVIEW
    if any(status == STATUS_NOT_ESTABLISHED for status in statuses):
        # Mix of supported + not established under AND → not fully established,
        # but call out review only when review exists (handled above).
        if any(status == STATUS_SUPPORTED for status in statuses):
            return STATUS_NOT_ESTABLISHED
        return STATUS_NOT_ESTABLISHED
    return STATUS_NOT_ESTABLISHED


def evaluate_patient_policy(
    db: Session,
    patient_id: str,
    *,
    policy_id: str = FICTIONAL_POLICY_ID,
    persist: bool = True,
    use_nli: bool | None = None,
) -> PolicyEvaluation:
    policy: PolicyDefinition = load_policy(policy_id)
    candidates = (
        db.query(EvidenceCandidate)
        .options(joinedload(EvidenceCandidate.document))
        .filter(
            EvidenceCandidate.patient_id == patient_id,
            EvidenceCandidate.policy_id == policy.id,
        )
        .order_by(
            EvidenceCandidate.requirement_id,
            EvidenceCandidate.relevance_score.desc(),
        )
        .all()
    )

    by_requirement: dict[str, list[EvidenceCandidate]] = {req.id: [] for req in policy.requirements}
    for candidate in candidates:
        by_requirement.setdefault(candidate.requirement_id, []).append(candidate)

    all_verdicts: list[CandidateVerdict] = []
    requirement_evals: list[RequirementEvaluation] = []

    for requirement in policy.requirements:
        req_candidates = by_requirement.get(requirement.id, [])
        verdicts = [
            verify_candidate(
                db,
                candidate,
                requirement,
                as_of_date=policy.as_of_date,
                use_nli=use_nli,
            )
            for candidate in req_candidates
        ]
        all_verdicts.extend(verdicts)
        requirement_evals.append(_requirement_status(requirement, verdicts))

        if persist:
            verdict_by_id = {v.candidate_id: v for v in verdicts}
            for candidate in req_candidates:
                candidate.verification_status = verdict_by_id[candidate.id].status

    if persist:
        db.commit()

    return PolicyEvaluation(
        policy_id=policy.id,
        policy_name=policy.name,
        disclaimer=policy.disclaimer,
        as_of_date=policy.as_of_date,
        logic=policy.logic,
        overall_status=_overall_status(policy.logic, requirement_evals),
        requirements=requirement_evals,
        candidate_verdicts=all_verdicts,
    )

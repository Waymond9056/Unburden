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
from app.services.status_vocab import (
    CANDIDATE_CONTRADICTION,
    CANDIDATE_INSUFFICIENT,
    CANDIDATE_SUPPORT,
    REQUIREMENT_READY,
    REQUIREMENT_NEEDS_REVIEW,
    STATUSES,
    canonicalize_status,
    model_status_from_probs,
)
from app.services.value_parsing import (
    extract_dates_from_text,
    find_numeric_mentions,
    parse_date_token,
    select_threshold_values,
)

# Re-export canonical statuses for existing imports.
STATUS_SUPPORT = CANDIDATE_SUPPORT
STATUS_INSUFFICIENT = CANDIDATE_INSUFFICIENT
STATUS_CONTRADICTION = CANDIDATE_CONTRADICTION
CANDIDATE_ACCEPTED = CANDIDATE_SUPPORT  # legacy alias
CANDIDATE_REJECTED = CANDIDATE_CONTRADICTION  # legacy alias
CANDIDATE_NEEDS_REVIEW = CANDIDATE_INSUFFICIENT  # legacy alias
STATUS_SUPPORTED = REQUIREMENT_READY  # legacy alias
STATUS_NOT_ESTABLISHED = REQUIREMENT_NEEDS_REVIEW  # legacy alias
STATUS_NEEDS_REVIEW = REQUIREMENT_NEEDS_REVIEW
STATUS_READY = REQUIREMENT_READY
STATUS_APPROVED = REQUIREMENT_READY  # legacy alias


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
    support_candidate_ids: list[str]
    insufficient_candidate_ids: list[str]
    contradiction_candidate_ids: list[str]

    # Legacy property aliases for transitional call sites.
    @property
    def accepted_candidate_ids(self) -> list[str]:
        return self.support_candidate_ids

    @property
    def review_candidate_ids(self) -> list[str]:
        return self.insufficient_candidate_ids

    @property
    def rejected_candidate_ids(self) -> list[str]:
        return self.contradiction_candidate_ids


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


def _nli_score_from_details(candidate: EvidenceCandidate, quote: str, requirement: RequirementDefinition):
    """Reuse persisted NLI probs so reload / status updates skip model inference."""
    from app.services.nli_deberta import NliScore, requirement_hypothesis

    details = _parse_details(candidate)
    raw = details.get("nli")
    if not isinstance(raw, dict):
        return None
    try:
        support = float(raw.get("support", raw.get("entailment")))
        insufficient = float(raw.get("insufficient", raw.get("neutral")))
        contradiction = float(raw["contradiction"])
    except (KeyError, TypeError, ValueError):
        return None
    predicted = (
        canonicalize_status(str(raw.get("predicted_label") or ""))
        or str(raw.get("predicted_label") or "")
        or CANDIDATE_INSUFFICIENT
    )
    return NliScore(
        premise=quote,
        hypothesis=requirement_hypothesis(requirement),
        support=support,
        insufficient=insufficient,
        contradiction=contradiction,
        predicted_label=predicted,
        model_name=str(raw.get("model_name") or "cached"),
    )


def _try_nli_score(
    quote: str,
    requirement: RequirementDefinition,
    *,
    candidate: EvidenceCandidate | None = None,
    force: bool = False,
):
    """Score passage↔requirement when optional ML deps are installed.

    Reuses `extracted_details.nli` when present unless `force=True`.
    """
    from app.services.nli_deberta import (
        NliDependenciesMissing,
        ml_dependencies_available,
        score_requirement_passage,
    )

    if candidate is not None and not force:
        cached = _nli_score_from_details(candidate, quote, requirement)
        if cached is not None:
            return cached

    if not ml_dependencies_available():
        return None
    settings = get_settings()
    model_name = (settings.nli_model_name or "").strip() or None
    try:
        if model_name:
            return score_requirement_passage(quote, requirement, model_name=model_name)
        return score_requirement_passage(quote, requirement)
    except NliDependenciesMissing:
        return None


def _attach_nli_details(candidate: EvidenceCandidate, score) -> None:
    """Persist display NLI probs on the candidate without changing verdicts."""
    details = _parse_details(candidate)
    from app.services.nli_deberta import resolve_nli_gate_thresholds

    support_min = None
    contradiction_min = None
    contradiction_margin = None
    try:
        contradiction_min, contradiction_margin, support_min = resolve_nli_gate_thresholds()
    except Exception:
        pass
    model_status = model_status_from_probs(
        float(score.support),
        float(score.insufficient),
        float(score.contradiction),
        support_min=support_min or 0.70,
        contradiction_min=contradiction_min or 0.45,
        contradiction_margin=contradiction_margin or 0.15,
    )
    details["nli"] = {
        "support": float(score.support),
        "insufficient": float(score.insufficient),
        "contradiction": float(score.contradiction),
        # Legacy keys for older clients.
        "entailment": float(score.support),
        "neutral": float(score.insufficient),
        "predicted_label": str(score.predicted_label),
        "model_status": model_status,
        "model_name": str(score.model_name),
        "support_probability": float(score.support),
    }
    candidate.extracted_details_json = json.dumps(details, ensure_ascii=False)


def clinician_override_status(candidate: EvidenceCandidate) -> str | None:
    details = _parse_details(candidate)
    raw = details.get("clinician_override")
    if isinstance(raw, dict):
        return canonicalize_status(raw.get("status"))
    if isinstance(raw, str):
        return canonicalize_status(raw)
    return None


def set_clinician_override(candidate: EvidenceCandidate, status: str) -> str:
    """Persist a clinician citation override and apply it as verification_status."""
    canonical = canonicalize_status(status)
    if canonical not in STATUSES:
        raise ValueError(
            f"Invalid status '{status}'. Expected one of: {', '.join(STATUSES)}"
        )
    details = _parse_details(candidate)
    details["clinician_override"] = {
        "status": canonical,
        "previous_status": canonicalize_status(candidate.verification_status)
        or candidate.verification_status,
    }
    candidate.extracted_details_json = json.dumps(details, ensure_ascii=False)
    candidate.verification_status = canonical
    return canonical


def clear_clinician_override(candidate: EvidenceCandidate) -> None:
    details = _parse_details(candidate)
    details.pop("clinician_override", None)
    candidate.extracted_details_json = json.dumps(details, ensure_ascii=False)


def model_status_for_candidate(candidate: EvidenceCandidate) -> str | None:
    details = _parse_details(candidate)
    nli = details.get("nli")
    if not isinstance(nli, dict):
        return None
    if "model_status" in nli:
        return canonicalize_status(str(nli["model_status"]))
    try:
        support = float(nli.get("support", nli.get("entailment", 0.0)))
        insufficient = float(nli.get("insufficient", nli.get("neutral", 0.0)))
        contradiction = float(nli.get("contradiction", 0.0))
    except (TypeError, ValueError):
        return canonicalize_status(str(nli.get("predicted_label") or ""))
    from app.services.nli_deberta import resolve_nli_gate_thresholds

    try:
        contradiction_min, contradiction_margin, support_min = resolve_nli_gate_thresholds()
    except Exception:
        contradiction_min, contradiction_margin, support_min = 0.45, 0.15, 0.70
    return model_status_from_probs(
        support,
        insufficient,
        contradiction,
        support_min=support_min,
        contradiction_min=contradiction_min,
        contradiction_margin=contradiction_margin,
    )


def display_status_for_candidate(candidate: EvidenceCandidate) -> str:
    """Clinician override > model cutoff prediction > Milestone-3 verification."""
    override = clinician_override_status(candidate)
    if override:
        return override
    model = model_status_for_candidate(candidate)
    if model:
        return model
    return (
        canonicalize_status(candidate.verification_status)
        or candidate.verification_status
        or CANDIDATE_INSUFFICIENT
    )


def _apply_nli_signal(
    quote: str,
    requirement: RequirementDefinition,
    *,
    score=None,
) -> CandidateVerdict | str | None:
    """Optional DeBERTa negation / support-note signal.

    Returns:
      - CandidateVerdict for reject/review short-circuit
      - str support note to append if math later accepts
      - None if NLI is unavailable or has no action
    Never performs date/numeric comparisons.
    """
    from app.services.nli_deberta import interpret_nli_verification_signal

    if score is None:
        score = _try_nli_score(quote, requirement)
    if score is None:
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
    force_nli: bool = False,
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

    # Display scores whenever ML is available; does not change verdicts by itself.
    # Prefer cached probs so page reload / clinician overrides stay snappy.
    nli_support_note: str | None = None
    nli_score = _try_nli_score(
        quote, requirement, candidate=candidate, force=force_nli
    )
    if nli_score is not None:
        _attach_nli_details(candidate, nli_score)

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
    if _nli_enabled(use_nli):
        nli_result = _apply_nli_signal(quote, requirement, score=nli_score)
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
    support = [v for v in verdicts if v.status == CANDIDATE_SUPPORT]
    insufficient = [v for v in verdicts if v.status == CANDIDATE_INSUFFICIENT]
    contradiction = [v for v in verdicts if v.status == CANDIDATE_CONTRADICTION]

    # READY only when there is ≥1 support and zero contradiction citations.
    if contradiction or not support:
        status = REQUIREMENT_NEEDS_REVIEW
    else:
        status = REQUIREMENT_READY

    return RequirementEvaluation(
        requirement_id=requirement.id,
        title=requirement.title,
        status=status,
        explanation="",
        suggested_document_types=list(requirement.suggested_document_types),
        support_candidate_ids=[v.candidate_id for v in support],
        insufficient_candidate_ids=[v.candidate_id for v in insufficient],
        contradiction_candidate_ids=[v.candidate_id for v in contradiction],
    )


def _overall_status(logic: str, requirement_evals: list[RequirementEvaluation]) -> str:
    statuses = [item.status for item in requirement_evals]
    if not statuses:
        return REQUIREMENT_NEEDS_REVIEW
    if logic.upper() == "OR":
        return (
            REQUIREMENT_READY
            if REQUIREMENT_READY in statuses
            else REQUIREMENT_NEEDS_REVIEW
        )
    # Default AND: every requirement must be READY.
    if all(status == REQUIREMENT_READY for status in statuses):
        return REQUIREMENT_READY
    return REQUIREMENT_NEEDS_REVIEW


def evaluate_patient_policy(
    db: Session,
    patient_id: str,
    *,
    policy_id: str = FICTIONAL_POLICY_ID,
    persist: bool = True,
    use_nli: bool | None = None,
    force_nli: bool = False,
) -> PolicyEvaluation:
    policy: PolicyDefinition = load_policy(policy_id)
    requirement_ids = [requirement.id for requirement in policy.requirements]
    candidates = (
        db.query(EvidenceCandidate)
        .options(joinedload(EvidenceCandidate.document))
        .filter(
            EvidenceCandidate.patient_id == patient_id,
            # Shared requirement ids can be retrieved under another insurer's policy_id.
            EvidenceCandidate.requirement_id.in_(requirement_ids or [""]),
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
                force_nli=force_nli,
            )
            for candidate in req_candidates
        ]
        # Rollup follows the same status the checklist paints:
        # clinician override > model cutoff > Milestone-3 verification.
        adjusted: list[CandidateVerdict] = []
        for candidate, verdict in zip(req_candidates, verdicts, strict=True):
            override = clinician_override_status(candidate)
            if not override:
                # So display_status fallback sees the fresh Milestone-3 result.
                candidate.verification_status = verdict.status
            rollup_status = display_status_for_candidate(candidate)
            reasons = list(verdict.reasons)
            if override:
                reasons.append(
                    f"Clinician override set status to {rollup_status}."
                )
            elif rollup_status != verdict.status:
                reasons.append(
                    f"Requirement rollup uses display status {rollup_status} "
                    f"over verification {verdict.status}."
                )
            adjusted.append(
                CandidateVerdict(
                    candidate_id=candidate.id,
                    status=rollup_status,
                    reasons=reasons,
                )
            )
        all_verdicts.extend(adjusted)
        requirement_evals.append(_requirement_status(requirement, adjusted))

        if persist:
            for candidate, verdict in zip(req_candidates, verdicts, strict=True):
                override = clinician_override_status(candidate)
                candidate.verification_status = override or verdict.status

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

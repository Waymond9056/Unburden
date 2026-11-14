"""Status vocabulary for citations + requirement rollups.

Citation / NLI / TREC (3-way):
  support | insufficient | contradiction

Requirement / overall rollup (2-way):
  READY        — ≥1 support citation and zero contradiction citations
  NEEDS_REVIEW — any contradiction citation, or no support citations
"""

from __future__ import annotations

STATUS_SUPPORT = "support"
STATUS_INSUFFICIENT = "insufficient"
STATUS_CONTRADICTION = "contradiction"

STATUSES = (STATUS_SUPPORT, STATUS_INSUFFICIENT, STATUS_CONTRADICTION)

# Layer aliases (identical values — keeps call sites readable).
CANDIDATE_SUPPORT = STATUS_SUPPORT
CANDIDATE_INSUFFICIENT = STATUS_INSUFFICIENT
CANDIDATE_CONTRADICTION = STATUS_CONTRADICTION

REQUIREMENT_READY = "READY"
REQUIREMENT_NEEDS_REVIEW = "NEEDS_REVIEW"

# Legacy aliases used by older rollup call sites.
REQUIREMENT_APPROVED = REQUIREMENT_READY
REQUIREMENT_SUPPORT = REQUIREMENT_READY
REQUIREMENT_INSUFFICIENT = REQUIREMENT_NEEDS_REVIEW
REQUIREMENT_CONTRADICTION = REQUIREMENT_NEEDS_REVIEW

TREC_TO_STATUS = {
    "definitely relevant": STATUS_SUPPORT,
    "not relevant": STATUS_INSUFFICIENT,
    "possibly relevant": STATUS_CONTRADICTION,
}

NLI_MODEL_TO_STATUS = {
    "entailment": STATUS_SUPPORT,
    "neutral": STATUS_INSUFFICIENT,
    "contradiction": STATUS_CONTRADICTION,
    "contradictory": STATUS_CONTRADICTION,
}

# Legacy strings still seen in older DB rows / caches (citation layer).
LEGACY_STATUS_TO_CANONICAL = {
    "accepted": STATUS_SUPPORT,
    "needs_review": STATUS_INSUFFICIENT,
    "rejected": STATUS_CONTRADICTION,
    "SUPPORTED": STATUS_SUPPORT,
    "NOT_ESTABLISHED": STATUS_CONTRADICTION,
    "entailment": STATUS_SUPPORT,
    "neutral": STATUS_INSUFFICIENT,
    "contradiction": STATUS_CONTRADICTION,
    **{status: status for status in STATUSES},
}

REQUIREMENT_STATUSES = (REQUIREMENT_READY, REQUIREMENT_NEEDS_REVIEW)


def canonicalize_status(raw: str | None) -> str | None:
    if raw is None:
        return None
    key = raw.strip()
    if not key:
        return None
    return LEGACY_STATUS_TO_CANONICAL.get(key) or LEGACY_STATUS_TO_CANONICAL.get(
        key.lower()
    )


def model_status_from_probs(
    support: float,
    insufficient: float,
    contradiction: float,
    *,
    support_min: float = 0.70,
    contradiction_min: float = 0.45,
    contradiction_margin: float = 0.15,
) -> str:
    """Map NLI probabilities to a display status using TREC-calibrated cutoffs."""
    second = sorted([support, insufficient, contradiction], reverse=True)[1]
    if contradiction >= contradiction_min and (contradiction - second) >= contradiction_margin:
        return STATUS_CONTRADICTION
    if support >= support_min:
        return STATUS_SUPPORT
    return STATUS_INSUFFICIENT

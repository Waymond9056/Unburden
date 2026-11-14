"""Experimental zero-shot NLI scoring for evidence candidates.

This module does NOT change Milestone 3 verification decisions. It scores whether
a passage (premise) supports a policy requirement statement (hypothesis).

Primary: MoritzLaurer/DeBERTa-v3-base-mnli-fever-anli
Optional biomedical second opinion: pritamdeka/PubMedBERT-MNLI-MedNLI
"""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.services.policy import RequirementDefinition
from app.services.status_vocab import (
    NLI_MODEL_TO_STATUS,
    STATUS_CONTRADICTION,
    STATUS_INSUFFICIENT,
    STATUS_SUPPORT,
    STATUSES,
)

DEFAULT_MODEL_NAME = "MoritzLaurer/DeBERTa-v3-base-mnli-fever-anli"
BIOMED_MODEL_NAME = "pritamdeka/PubMedBERT-MNLI-MedNLI"

# Canonical Unburden labels (parallel with citation + requirement statuses).
LABEL_SUPPORT = STATUS_SUPPORT
LABEL_INSUFFICIENT = STATUS_INSUFFICIENT
LABEL_CONTRADICTION = STATUS_CONTRADICTION
NLI_LABELS = STATUSES

# Legacy aliases used by older tests / scripts.
LABEL_ENTAILMENT = LABEL_SUPPORT
LABEL_NEUTRAL = LABEL_INSUFFICIENT

_MODEL_LOCK = threading.Lock()
_MODEL_CACHE: dict[str, tuple[Any, Any]] = {}


class NliDependenciesMissing(RuntimeError):
    """Raised when torch/transformers are not installed."""


@dataclass(frozen=True)
class NliScore:
    premise: str
    hypothesis: str
    support: float
    insufficient: float
    contradiction: float
    predicted_label: str
    model_name: str

    # Legacy probability aliases (model-native names).
    @property
    def entailment(self) -> float:
        return self.support

    @property
    def neutral(self) -> float:
        return self.insufficient

    def as_dict(self) -> dict[str, Any]:
        return {
            "premise": self.premise,
            "hypothesis": self.hypothesis,
            "support": self.support,
            "insufficient": self.insufficient,
            "contradiction": self.contradiction,
            "entailment": self.support,
            "neutral": self.insufficient,
            "predicted_label": self.predicted_label,
            "model_name": self.model_name,
        }


@dataclass(frozen=True)
class EnsembleNliScore:
    premise: str
    hypothesis: str
    deberta: NliScore
    biomed: NliScore
    predicted_label: str
    agreed: bool
    model_name: str = "ensemble:deberta+pubmedbert-mednli"

    def as_dict(self) -> dict[str, Any]:
        return {
            "premise": self.premise,
            "hypothesis": self.hypothesis,
            "predicted_label": self.predicted_label,
            "agreed": self.agreed,
            "model_name": self.model_name,
            "deberta": self.deberta.as_dict(),
            "biomed": self.biomed.as_dict(),
        }


# Short claim forms work better for NLI than long policy-rule descriptions.
# Keep these semantic; dates/thresholds still belong to Milestone 3.
_HYPOTHESIS_BY_REQUIREMENT_ID: dict[str, str] = {
    "documented_severe_asthma": "The patient has documented severe persistent asthma.",
    "prior_controller_therapy": (
        "The patient previously received high-dose inhaled corticosteroid controller therapy."
    ),
    "qualifying_eosinophil_result": (
        "The patient has a qualifying absolute eosinophil count of at least 300 cells per microliter."
    ),
}


def requirement_hypothesis(requirement: RequirementDefinition) -> str:
    """Turn a policy requirement into an NLI hypothesis claim."""
    override = _HYPOTHESIS_BY_REQUIREMENT_ID.get(requirement.id)
    if override:
        return override
    return requirement.description.strip()


def _contains_any(text: str, needles: tuple[str, ...]) -> bool:
    lowered = text.lower()
    return any(needle.lower() in lowered for needle in needles)


def lexical_support_label(passage: str, requirement: RequirementDefinition) -> str:
    """Keyword baseline mirroring the semantic bits of Milestone 3 rules.

    This intentionally ignores dates, numeric thresholds, and document-type gates
    so it can be compared apples-to-apples with zero-shot NLI on support semantics.
    """
    if requirement.reject_if_quote_matches_any and _contains_any(
        passage, requirement.reject_if_quote_matches_any
    ):
        return LABEL_CONTRADICTION
    if requirement.ambiguous_if_quote_matches_any and _contains_any(
        passage, requirement.ambiguous_if_quote_matches_any
    ):
        return LABEL_NEUTRAL
    if requirement.must_match_any:
        if _contains_any(passage, requirement.must_match_any):
            return LABEL_ENTAILMENT
        return LABEL_NEUTRAL
    return LABEL_NEUTRAL


def ml_dependencies_available() -> bool:
    try:
        import torch  # noqa: F401
        import transformers  # noqa: F401
    except ImportError:
        return False
    return True


def _ensure_model(model_name: str = DEFAULT_MODEL_NAME) -> tuple[Any, Any]:
    cached = _MODEL_CACHE.get(model_name)
    if cached is not None:
        return cached

    with _MODEL_LOCK:
        cached = _MODEL_CACHE.get(model_name)
        if cached is not None:
            return cached
        try:
            import torch
            from transformers import AutoModelForSequenceClassification, AutoTokenizer
        except ImportError as exc:
            raise NliDependenciesMissing(
                "Install optional ML deps first: pip install -r requirements-ml.txt"
            ) from exc

        tokenizer = AutoTokenizer.from_pretrained(model_name)
        model = AutoModelForSequenceClassification.from_pretrained(model_name)
        model.eval()
        if torch.cuda.is_available():
            model = model.to("cuda")
        _MODEL_CACHE[model_name] = (tokenizer, model)
        return tokenizer, model


def _normalize_label(raw: str) -> str:
    label = raw.lower().strip()
    if label in NLI_MODEL_TO_STATUS:
        return NLI_MODEL_TO_STATUS[label]
    if label in STATUSES:
        return label
    return label


def score_passage(
    passage: str,
    hypothesis: str,
    *,
    model_name: str = DEFAULT_MODEL_NAME,
) -> NliScore:
    """Score whether `passage` supports `hypothesis` with an NLI checkpoint."""
    import torch

    tokenizer, model = _ensure_model(model_name)
    inputs = tokenizer(
        passage,
        hypothesis,
        return_tensors="pt",
        truncation=True,
        max_length=512,
    )
    device = next(model.parameters()).device
    inputs = {key: value.to(device) for key, value in inputs.items()}

    with torch.inference_mode():
        logits = model(**inputs).logits[0]
        probs = torch.softmax(logits, dim=-1)

    id2label = {int(k): str(v) for k, v in model.config.id2label.items()}
    score_map = {
        LABEL_SUPPORT: 0.0,
        LABEL_INSUFFICIENT: 0.0,
        LABEL_CONTRADICTION: 0.0,
    }
    for index, probability in enumerate(probs.tolist()):
        label = _normalize_label(id2label.get(index, str(index)))
        if label in score_map:
            score_map[label] = float(probability)

    predicted = max(score_map.items(), key=lambda item: item[1])[0]
    return NliScore(
        premise=passage,
        hypothesis=hypothesis,
        support=score_map[LABEL_SUPPORT],
        insufficient=score_map[LABEL_INSUFFICIENT],
        contradiction=score_map[LABEL_CONTRADICTION],
        predicted_label=predicted,
        model_name=model_name,
    )


def score_requirement_passage(
    passage: str,
    requirement: RequirementDefinition,
    *,
    model_name: str = DEFAULT_MODEL_NAME,
) -> NliScore:
    return score_passage(
        passage,
        requirement_hypothesis(requirement),
        model_name=model_name,
    )


def ensemble_score_passage(
    passage: str,
    hypothesis: str,
    *,
    general_model: str = DEFAULT_MODEL_NAME,
    biomed_model: str = BIOMED_MODEL_NAME,
) -> EnsembleNliScore:
    """Combine DeBERTa + biomedical MedNLI.

    Agreement → use the shared label.
    Disagreement → neutral (route to human review; don't guess).
    Probabilities are averaged only for reporting when models agree; on
    disagreement the predicted label is forced to neutral.
    """
    general = score_passage(passage, hypothesis, model_name=general_model)
    biomed = score_passage(passage, hypothesis, model_name=biomed_model)
    agreed = general.predicted_label == biomed.predicted_label
    predicted = general.predicted_label if agreed else LABEL_NEUTRAL
    return EnsembleNliScore(
        premise=passage,
        hypothesis=hypothesis,
        deberta=general,
        biomed=biomed,
        predicted_label=predicted,
        agreed=agreed,
    )


def ensemble_score_requirement_passage(
    passage: str,
    requirement: RequirementDefinition,
) -> EnsembleNliScore:
    return ensemble_score_passage(passage, requirement_hypothesis(requirement))


@dataclass(frozen=True)
class NliVerificationSignal:
    """How DeBERTa should influence Milestone 3 — never replaces date/numeric math."""

    action: str  # "reject" | "review" | "support_note" | "none"
    reason: str
    score: NliScore


def load_calibrated_thresholds() -> dict[str, float] | None:
    """Load TREC-calibrated gate thresholds if present (no weight updates)."""
    path = (
        Path(__file__).resolve().parents[2]
        / "benchmarks"
        / "nli_calibrated_thresholds.json"
    )
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        thresholds = payload.get("thresholds") or {}
        return {
            "contradiction_min": float(thresholds["nli_contradiction_min"]),
            "contradiction_margin": float(thresholds["nli_contradiction_margin"]),
            "entailment_min": float(thresholds["nli_entailment_min"]),
        }
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        return None


def resolve_nli_gate_thresholds(
    *,
    contradiction_min: float | None = None,
    contradiction_margin: float | None = None,
    entailment_min: float | None = None,
) -> tuple[float, float, float]:
    """Explicit args > env overrides > TREC-calibrated file > shipped defaults."""
    import os

    from app.core.config import get_settings

    settings = get_settings()
    calibrated = load_calibrated_thresholds() or {}

    def _pick(
        explicit: float | None,
        env_key: str,
        calibrated_key: str,
        settings_value: float,
        default: float,
    ) -> float:
        if explicit is not None:
            return float(explicit)
        if os.environ.get(env_key):
            return float(settings_value)
        if calibrated_key in calibrated:
            return float(calibrated[calibrated_key])
        return float(settings_value if settings_value is not None else default)

    return (
        _pick(
            contradiction_min,
            "NLI_CONTRADICTION_MIN",
            "contradiction_min",
            settings.nli_contradiction_min,
            0.55,
        ),
        _pick(
            contradiction_margin,
            "NLI_CONTRADICTION_MARGIN",
            "contradiction_margin",
            settings.nli_contradiction_margin,
            0.15,
        ),
        _pick(
            entailment_min,
            "NLI_ENTAILMENT_MIN",
            "entailment_min",
            settings.nli_entailment_min,
            0.80,
        ),
    )


def interpret_nli_verification_signal(
    score: NliScore,
    *,
    contradiction_min: float | None = None,
    contradiction_margin: float | None = None,
    entailment_min: float | None = None,
) -> NliVerificationSignal:
    """Map NLI probs to a gated verification action.

    - Strong contradiction (argmax + margin) → reject paraphrased negations
    - Weak contradiction → needs_review (avoid false rejects)
    - Strong entailment → support note only (Milestone 3 math still decides accept)
    """
    contradiction_min, contradiction_margin, entailment_min = resolve_nli_gate_thresholds(
        contradiction_min=contradiction_min,
        contradiction_margin=contradiction_margin,
        entailment_min=entailment_min,
    )
    second = sorted(
        [score.entailment, score.neutral, score.contradiction], reverse=True
    )[1]
    if (
        score.predicted_label == LABEL_CONTRADICTION
        and score.contradiction >= contradiction_min
    ):
        if score.contradiction - second >= contradiction_margin:
            return NliVerificationSignal(
                action="reject",
                reason=(
                    "DeBERTa NLI contradiction signal: passage appears to negate the "
                    f"requirement claim (C={score.contradiction:.2f})."
                ),
                score=score,
            )
        return NliVerificationSignal(
            action="review",
            reason=(
                "DeBERTa NLI weak contradiction signal: possible negation needs "
                f"clinician review (C={score.contradiction:.2f})."
            ),
            score=score,
        )
    if (
        score.predicted_label == LABEL_ENTAILMENT
        and score.entailment >= entailment_min
    ):
        return NliVerificationSignal(
            action="support_note",
            reason=(
                "DeBERTa NLI high-precision support signal "
                f"(E={score.entailment:.2f}); structured checks still required."
            ),
            score=score,
        )
    return NliVerificationSignal(action="none", reason="", score=score)

"""Experimental zero-shot DeBERTa-v3 NLI scoring for evidence candidates.

This module does NOT change Milestone 3 verification decisions. It scores whether
a passage (premise) supports a policy requirement statement (hypothesis).

Model: MoritzLaurer/DeBERTa-v3-base-mnli-fever-anli
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Any

from app.services.policy import RequirementDefinition

DEFAULT_MODEL_NAME = "MoritzLaurer/DeBERTa-v3-base-mnli-fever-anli"

LABEL_ENTAILMENT = "entailment"
LABEL_NEUTRAL = "neutral"
LABEL_CONTRADICTION = "contradiction"
NLI_LABELS = (LABEL_ENTAILMENT, LABEL_NEUTRAL, LABEL_CONTRADICTION)

_MODEL_LOCK = threading.Lock()
_TOKENIZER: Any = None
_MODEL: Any = None
_MODEL_NAME_LOADED: str | None = None


class NliDependenciesMissing(RuntimeError):
    """Raised when torch/transformers are not installed."""


@dataclass(frozen=True)
class NliScore:
    premise: str
    hypothesis: str
    entailment: float
    neutral: float
    contradiction: float
    predicted_label: str
    model_name: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "premise": self.premise,
            "hypothesis": self.hypothesis,
            "entailment": self.entailment,
            "neutral": self.neutral,
            "contradiction": self.contradiction,
            "predicted_label": self.predicted_label,
            "model_name": self.model_name,
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
    "recent_exacerbation_history": (
        "The patient had a recent asthma exacerbation treated with systemic corticosteroids "
        "or emergency care."
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
    global _TOKENIZER, _MODEL, _MODEL_NAME_LOADED
    if _MODEL is not None and _TOKENIZER is not None and _MODEL_NAME_LOADED == model_name:
        return _TOKENIZER, _MODEL

    with _MODEL_LOCK:
        if _MODEL is not None and _TOKENIZER is not None and _MODEL_NAME_LOADED == model_name:
            return _TOKENIZER, _MODEL
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
        # Keep on CPU for the first experiment unless CUDA is obviously available.
        if torch.cuda.is_available():
            model = model.to("cuda")
        _TOKENIZER = tokenizer
        _MODEL = model
        _MODEL_NAME_LOADED = model_name
        return _TOKENIZER, _MODEL


def score_passage(
    passage: str,
    hypothesis: str,
    *,
    model_name: str = DEFAULT_MODEL_NAME,
) -> NliScore:
    """Score whether `passage` supports `hypothesis` with zero-shot DeBERTa NLI."""
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

    id2label = {int(k): str(v).lower() for k, v in model.config.id2label.items()}
    score_map = {LABEL_ENTAILMENT: 0.0, LABEL_NEUTRAL: 0.0, LABEL_CONTRADICTION: 0.0}
    for index, probability in enumerate(probs.tolist()):
        label = id2label.get(index, str(index))
        if label in score_map:
            score_map[label] = float(probability)

    predicted = max(score_map.items(), key=lambda item: item[1])[0]
    return NliScore(
        premise=passage,
        hypothesis=hypothesis,
        entailment=score_map[LABEL_ENTAILMENT],
        neutral=score_map[LABEL_NEUTRAL],
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

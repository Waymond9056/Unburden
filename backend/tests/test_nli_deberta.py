from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.services.nli_deberta import (
    LABEL_CONTRADICTION,
    LABEL_ENTAILMENT,
    LABEL_NEUTRAL,
    lexical_support_label,
    ml_dependencies_available,
    requirement_hypothesis,
)
from app.services.policy import REQUIREMENTS_BY_ID

BENCHMARK_PATH = (
    Path(__file__).resolve().parents[1] / "benchmarks" / "nli_support_benchmark.json"
)


def test_benchmark_dataset_is_well_formed() -> None:
    payload = json.loads(BENCHMARK_PATH.read_text(encoding="utf-8"))
    examples = payload["examples"]
    assert len(examples) >= 30
    labels = {item["gold_label"] for item in examples}
    assert labels == {LABEL_ENTAILMENT, LABEL_NEUTRAL, LABEL_CONTRADICTION}
    for item in examples:
        assert item["requirement_id"] in REQUIREMENTS_BY_ID
        assert item["passage"].strip()
        assert item["gold_label"] in labels


def test_lexical_baseline_flags_misleading_nasal_controller() -> None:
    requirement = REQUIREMENTS_BY_ID["prior_controller_therapy"]
    passage = (
        "Patient has seasonal allergic rhinitis. Inhaled corticosteroid spray "
        "for nasal symptoms was discussed."
    )
    assert lexical_support_label(passage, requirement) == LABEL_CONTRADICTION


def test_lexical_baseline_accepts_keyword_hit() -> None:
    requirement = REQUIREMENTS_BY_ID["documented_severe_asthma"]
    passage = "Assessment: Severe persistent asthma, ICD-10 J45.50."
    assert lexical_support_label(passage, requirement) == LABEL_ENTAILMENT


def test_lexical_baseline_marks_ambiguous_asthma() -> None:
    requirement = REQUIREMENTS_BY_ID["documented_severe_asthma"]
    passage = "Possible asthma; confirm with spirometry."
    assert lexical_support_label(passage, requirement) == LABEL_NEUTRAL


def test_requirement_hypothesis_uses_policy_description() -> None:
    requirement = REQUIREMENTS_BY_ID["qualifying_eosinophil_result"]
    assert "eosinophil" in requirement_hypothesis(requirement).lower()


@pytest.mark.skipif(
    not ml_dependencies_available(),
    reason="optional ML deps (torch/transformers) not installed",
)
def test_deberta_scores_clear_controller_support() -> None:
    from app.services.nli_deberta import score_requirement_passage

    requirement = REQUIREMENTS_BY_ID["prior_controller_therapy"]
    passage = (
        "Patient completed six months of high-dose inhaled corticosteroid "
        "controller therapy with fluticasone-salmeterol."
    )
    score = score_requirement_passage(passage, requirement)
    assert score.predicted_label == LABEL_ENTAILMENT
    assert score.entailment > score.contradiction
    assert score.entailment > score.neutral

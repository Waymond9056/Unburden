#!/usr/bin/env python3
"""Calibrate DeBERTa contradiction/entailment thresholds on TREC Clinical Trials.

Uses araag2/TREC_Clinical-Trials (2021_processed) — 3-way labels, no weight updates.

Label map (HF string labels ↔ Unburden NLI framing):
  definitely relevant → entailment (eligible / support)
  possibly relevant   → contradiction (excluded / ruled out)
  not relevant        → neutral (off-topic / insufficient)

Optimizes for Unburden's gate:
  - catch contradictions (negations) with reject/review
  - keep reject precision high (false rejects are costly)
  - keep strong-entailment notes precise

Usage (from backend/):
  python scripts/calibrate_nli_thresholds.py
  python scripts/calibrate_nli_thresholds.py --max-per-class 400
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.services.nli_deberta import (  # noqa: E402
    DEFAULT_MODEL_NAME,
    interpret_nli_verification_signal,
    ml_dependencies_available,
    score_passage,
)

OUT_PATH = ROOT / "benchmarks" / "nli_calibrated_thresholds.json"
CACHE_PATH = ROOT / "benchmarks" / "trec_calibration_score_cache.jsonl"
SYNTH_PATH = ROOT / "benchmarks" / "nli_support_benchmark.json"

LABEL_MAP = {
    "definitely relevant": "entailment",
    "possibly relevant": "contradiction",
    "not relevant": "neutral",
}


@dataclass(frozen=True)
class ScoredPair:
    gold: str
    entailment: float
    neutral: float
    contradiction: float
    predicted_label: str


def _truncate(text: str, max_chars: int = 1600) -> str:
    text = " ".join((text or "").split())
    return text if len(text) <= max_chars else text[: max_chars - 3].rstrip() + "..."


def _load_trec_sample(max_per_class: int, seed: int) -> list[dict]:
    from datasets import load_dataset

    ds = load_dataset("araag2/TREC_Clinical-Trials", "2021_processed", split="test")
    by_label: dict[str, list[dict]] = defaultdict(list)
    for row in ds:
        gold = LABEL_MAP.get(row["Label"])
        if gold is None:
            continue
        by_label[gold].append(
            {
                "id": f"trec2021-{row['id']}",
                "premise": _truncate(row["Patient"]),
                "hypothesis": _truncate(row["Eligibility"]),
                "gold": gold,
            }
        )

    rng = random.Random(seed)
    sample: list[dict] = []
    for gold, rows in by_label.items():
        rng.shuffle(rows)
        sample.extend(rows[:max_per_class])
    rng.shuffle(sample)
    print("TREC sample:", dict(Counter(r["gold"] for r in sample)))
    return sample


def _score_pairs(pairs: list[dict], model_name: str) -> list[ScoredPair]:
    scored: list[ScoredPair] = []
    for i, pair in enumerate(pairs, start=1):
        result = score_passage(pair["premise"], pair["hypothesis"], model_name=model_name)
        scored.append(
            ScoredPair(
                gold=pair["gold"],
                entailment=result.entailment,
                neutral=result.neutral,
                contradiction=result.contradiction,
                predicted_label=result.predicted_label,
            )
        )
        if i % 50 == 0 or i == len(pairs):
            print(f"  scored {i}/{len(pairs)}")
    return scored


def _action_for(
    pair: ScoredPair,
    *,
    contradiction_min: float,
    contradiction_margin: float,
    entailment_min: float,
) -> str:
    from app.services.nli_deberta import NliScore

    score = NliScore(
        premise="",
        hypothesis="",
        entailment=pair.entailment,
        neutral=pair.neutral,
        contradiction=pair.contradiction,
        predicted_label=pair.predicted_label,
        model_name="calibration",
    )
    return interpret_nli_verification_signal(
        score,
        contradiction_min=contradiction_min,
        contradiction_margin=contradiction_margin,
        entailment_min=entailment_min,
    ).action


def _evaluate(
    pairs: list[ScoredPair],
    *,
    contradiction_min: float,
    contradiction_margin: float,
    entailment_min: float,
) -> dict:
    actions = [
        _action_for(
            pair,
            contradiction_min=contradiction_min,
            contradiction_margin=contradiction_margin,
            entailment_min=entailment_min,
        )
        for pair in pairs
    ]

    # Reject/review both count as "caught negation-ish" for recall; reject alone for precision.
    gold_contra = [i for i, p in enumerate(pairs) if p.gold == "contradiction"]
    gold_entail = [i for i, p in enumerate(pairs) if p.gold == "entailment"]
    gold_neutral = [i for i, p in enumerate(pairs) if p.gold == "neutral"]

    reject_idx = [i for i, a in enumerate(actions) if a == "reject"]
    catch_idx = [i for i, a in enumerate(actions) if a in {"reject", "review"}]
    support_idx = [i for i, a in enumerate(actions) if a == "support_note"]

    def _safe_div(n: float, d: float) -> float:
        return n / d if d else 0.0

    contra_recall_reject = _safe_div(
        sum(1 for i in gold_contra if actions[i] == "reject"), len(gold_contra)
    )
    contra_recall_catch = _safe_div(
        sum(1 for i in gold_contra if actions[i] in {"reject", "review"}), len(gold_contra)
    )
    reject_precision = _safe_div(
        sum(1 for i in reject_idx if pairs[i].gold == "contradiction"), len(reject_idx)
    )
    false_reject_on_support = _safe_div(
        sum(1 for i in gold_entail if actions[i] == "reject"), len(gold_entail)
    )
    false_reject_on_neutral = _safe_div(
        sum(1 for i in gold_neutral if actions[i] == "reject"), len(gold_neutral)
    )
    support_precision = _safe_div(
        sum(1 for i in support_idx if pairs[i].gold == "entailment"), len(support_idx)
    )
    support_recall = _safe_div(
        sum(1 for i in gold_entail if actions[i] == "support_note"), len(gold_entail)
    )

    # Objective: prioritize precise contradiction rejects, then recall, penalize false rejects.
    f1_reject = _safe_div(
        2 * reject_precision * contra_recall_reject,
        reject_precision + contra_recall_reject,
    )
    objective = (
        f1_reject
        + 0.25 * contra_recall_catch
        + 0.15 * support_precision
        - 0.80 * false_reject_on_support
        - 0.40 * false_reject_on_neutral
    )

    return {
        "contradiction_min": contradiction_min,
        "contradiction_margin": contradiction_margin,
        "entailment_min": entailment_min,
        "objective": objective,
        "reject_precision": reject_precision,
        "contra_recall_reject": contra_recall_reject,
        "contra_recall_catch": contra_recall_catch,
        "false_reject_on_support": false_reject_on_support,
        "false_reject_on_neutral": false_reject_on_neutral,
        "support_precision": support_precision,
        "support_recall": support_recall,
        "n_reject": len(reject_idx),
        "n_catch": len(catch_idx),
        "n_support_note": len(support_idx),
        "action_dist": dict(Counter(actions)),
    }


def _sweep(pairs: list[ScoredPair]) -> list[dict]:
    results = []
    for c_min in [0.45, 0.55, 0.65, 0.75, 0.85, 0.90]:
        for margin in [0.05, 0.10, 0.15, 0.20, 0.25, 0.30]:
            for e_min in [0.70, 0.80, 0.90, 0.95]:
                results.append(
                    _evaluate(
                        pairs,
                        contradiction_min=c_min,
                        contradiction_margin=margin,
                        entailment_min=e_min,
                    )
                )
    results.sort(key=lambda row: row["objective"], reverse=True)
    return results


def _score_synthetic(model_name: str) -> list[ScoredPair]:
    from app.services.nli_deberta import requirement_hypothesis
    from app.services.policy import REQUIREMENTS_BY_ID

    payload = json.loads(SYNTH_PATH.read_text(encoding="utf-8"))
    pairs = []
    for ex in payload["examples"]:
        requirement = REQUIREMENTS_BY_ID[ex["requirement_id"]]
        result = score_passage(
            ex["passage"],
            requirement_hypothesis(requirement),
            model_name=model_name,
        )
        pairs.append(
            ScoredPair(
                gold=ex["gold_label"],
                entailment=result.entailment,
                neutral=result.neutral,
                contradiction=result.contradiction,
                predicted_label=result.predicted_label,
            )
        )
    return pairs


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-per-class", type=int, default=250)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--model", default=DEFAULT_MODEL_NAME)
    parser.add_argument("--reuse-cache", action="store_true")
    args = parser.parse_args()

    if not ml_dependencies_available():
        print("Install ML deps: pip install -r requirements-ml.txt", file=sys.stderr)
        return 1

    if args.reuse_cache and CACHE_PATH.exists():
        print(f"Reusing score cache {CACHE_PATH}")
        scored = [
            ScoredPair(**json.loads(line))
            for line in CACHE_PATH.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    else:
        pairs = _load_trec_sample(args.max_per_class, args.seed)
        print(f"Scoring {len(pairs)} TREC pairs with {args.model} (no training)...")
        scored = _score_pairs(pairs, args.model)
        with CACHE_PATH.open("w", encoding="utf-8") as handle:
            for row in scored:
                handle.write(json.dumps(asdict(row)) + "\n")
        print(f"Wrote score cache → {CACHE_PATH}")

    # Hold out 20% for reporting after selecting on 80%.
    rng = random.Random(args.seed)
    idx = list(range(len(scored)))
    rng.shuffle(idx)
    cut = int(0.8 * len(idx))
    fit = [scored[i] for i in idx[:cut]]
    hold = [scored[i] for i in idx[cut:]]

    baseline = _evaluate(
        hold,
        contradiction_min=0.55,
        contradiction_margin=0.15,
        entailment_min=0.80,
    )
    sweep = _sweep(fit)
    best = sweep[0]
    hold_best = _evaluate(
        hold,
        contradiction_min=best["contradiction_min"],
        contradiction_margin=best["contradiction_margin"],
        entailment_min=best["entailment_min"],
    )

    print("\n=== Baseline thresholds on TREC holdout ===")
    print(
        f"c_min=0.55 margin=0.15 e_min=0.80  "
        f"reject_P={baseline['reject_precision']:.3f}  "
        f"contra_R={baseline['contra_recall_reject']:.3f}  "
        f"false_reject_support={baseline['false_reject_on_support']:.3f}  "
        f"obj={baseline['objective']:.3f}"
    )
    print("\n=== Best calibrated thresholds (fit → holdout) ===")
    print(
        f"c_min={best['contradiction_min']:.2f} "
        f"margin={best['contradiction_margin']:.2f} "
        f"e_min={best['entailment_min']:.2f}"
    )
    print(
        f"holdout reject_P={hold_best['reject_precision']:.3f}  "
        f"contra_R={hold_best['contra_recall_reject']:.3f}  "
        f"false_reject_support={hold_best['false_reject_on_support']:.3f}  "
        f"obj={hold_best['objective']:.3f}"
    )

    print("\nScoring Unburden synthetic benchmark with calibrated thresholds...")
    synth = _score_synthetic(args.model)
    synth_base = _evaluate(
        synth, contradiction_min=0.55, contradiction_margin=0.15, entailment_min=0.80
    )
    synth_best = _evaluate(
        synth,
        contradiction_min=best["contradiction_min"],
        contradiction_margin=best["contradiction_margin"],
        entailment_min=best["entailment_min"],
    )
    print(
        f"synthetic baseline obj={synth_base['objective']:.3f} "
        f"reject_P={synth_base['reject_precision']:.3f} "
        f"contra_R={synth_base['contra_recall_reject']:.3f}"
    )
    print(
        f"synthetic calibrated obj={synth_best['objective']:.3f} "
        f"reject_P={synth_best['reject_precision']:.3f} "
        f"contra_R={synth_best['contra_recall_reject']:.3f}"
    )

    payload = {
        "calibrated_at": datetime.now(timezone.utc).isoformat(),
        "model_name": args.model,
        "dataset": "araag2/TREC_Clinical-Trials:2021_processed",
        "label_map": LABEL_MAP,
        "n_fit": len(fit),
        "n_holdout": len(hold),
        "thresholds": {
            "nli_contradiction_min": best["contradiction_min"],
            "nli_contradiction_margin": best["contradiction_margin"],
            "nli_entailment_min": best["entailment_min"],
        },
        "baseline_thresholds": {
            "nli_contradiction_min": 0.55,
            "nli_contradiction_margin": 0.15,
            "nli_entailment_min": 0.80,
        },
        "trec_holdout_baseline": baseline,
        "trec_holdout_calibrated": hold_best,
        "synthetic_baseline": synth_base,
        "synthetic_calibrated": synth_best,
        "top5_candidates": sweep[:5],
        "notes": [
            "No model weights were updated — thresholds only.",
            "Use these values via env vars or defaults in config.py.",
        ],
    }
    OUT_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"\nWrote {OUT_PATH}")
    print(
        "\nSuggested env:\n"
        f"NLI_CONTRADICTION_MIN={best['contradiction_min']}\n"
        f"NLI_CONTRADICTION_MARGIN={best['contradiction_margin']}\n"
        f"NLI_ENTAILMENT_MIN={best['entailment_min']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

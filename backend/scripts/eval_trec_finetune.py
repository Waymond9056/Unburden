#!/usr/bin/env python3
"""Compare zero-shot DeBERTa vs TREC-finetuned DeBERTa on held-out sets.

Evaluates:
  1) TREC NLI4PR test split (real clinical-trials eligibility pairs)
  2) Unburden synthetic NLI benchmark
  3) Unburden M3+NLI architecture cases (signal labels only)

Usage:
  python scripts/eval_trec_finetune.py
  python scripts/eval_trec_finetune.py --finetuned backend/models/deberta-trec-nli
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.services.nli_deberta import (  # noqa: E402
    DEFAULT_MODEL_NAME,
    requirement_hypothesis,
    score_passage,
)
from app.services.policy import REQUIREMENTS_BY_ID  # noqa: E402

TREC_TEST = ROOT / "benchmarks" / "trec_nli" / "test.jsonl"
SYNTH = ROOT / "benchmarks" / "nli_support_benchmark.json"
ARCH = ROOT / "benchmarks" / "verification_architecture_benchmark.json"
DEFAULT_FT = ROOT / "models" / "deberta-trec-nli"


def _metrics(y_true: list[str], y_pred: list[str]) -> dict:
    labels = sorted(set(y_true) | set(y_pred))
    correct = sum(a == b for a, b in zip(y_true, y_pred, strict=True))
    acc = correct / len(y_true) if y_true else 0.0
    f1s = []
    per = {}
    for label in labels:
        tp = sum(t == label and p == label for t, p in zip(y_true, y_pred, strict=True))
        fp = sum(t != label and p == label for t, p in zip(y_true, y_pred, strict=True))
        fn = sum(t == label and p != label for t, p in zip(y_true, y_pred, strict=True))
        prec = tp / (tp + fp) if tp + fp else 0.0
        rec = tp / (tp + fn) if tp + fn else 0.0
        f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0.0
        per[label] = {"precision": prec, "recall": rec, "f1": f1, "support": sum(t == label for t in y_true)}
        f1s.append(f1)
    return {
        "accuracy": acc,
        "correct": correct,
        "total": len(y_true),
        "macro_f1": sum(f1s) / len(f1s) if f1s else 0.0,
        "per_label": per,
        "pred_dist": dict(Counter(y_pred)),
    }


def _print(title: str, metrics: dict) -> None:
    print(f"\n=== {title} ===")
    print(
        f"accuracy={metrics['accuracy']:.3f} ({metrics['correct']}/{metrics['total']})  "
        f"macro_f1={metrics['macro_f1']:.3f}  preds={metrics['pred_dist']}"
    )


def _eval_pairs(pairs: list[tuple[str, str, str]], model_name: str) -> dict:
    gold, pred = [], []
    for premise, hypothesis, label in pairs:
        score = score_passage(premise, hypothesis, model_name=model_name)
        gold.append(label)
        pred.append(score.predicted_label)
    return _metrics(gold, pred)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--finetuned", type=Path, default=DEFAULT_FT)
    parser.add_argument("--max-trec-test", type=int, default=400)
    args = parser.parse_args()

    if not args.finetuned.exists():
        print(f"Missing fine-tuned model at {args.finetuned}", file=sys.stderr)
        print("Run prepare + finetune scripts first.", file=sys.stderr)
        return 1
    if not TREC_TEST.exists():
        print("Missing TREC test split. Run prepare_trec_nli_splits.py", file=sys.stderr)
        return 1

    trec_rows = [json.loads(line) for line in TREC_TEST.read_text(encoding="utf-8").splitlines() if line]
    if args.max_trec_test and len(trec_rows) > args.max_trec_test:
        trec_rows = trec_rows[: args.max_trec_test]
    trec_pairs = [(r["premise"], r["hypothesis"], r["label"]) for r in trec_rows]

    synth = json.loads(SYNTH.read_text(encoding="utf-8"))["examples"]
    synth_pairs = [
        (
            ex["passage"],
            requirement_hypothesis(REQUIREMENTS_BY_ID[ex["requirement_id"]]),
            ex["gold_label"],
        )
        for ex in synth
    ]

    models = {
        "zero-shot": DEFAULT_MODEL_NAME,
        "trec-finetuned": str(args.finetuned),
    }
    report = {}
    for name, model_name in models.items():
        print(f"\n##### Model: {name} ({model_name}) #####")
        trec_m = _eval_pairs(trec_pairs, model_name)
        synth_m = _eval_pairs(synth_pairs, model_name)
        _print(f"{name} on TREC test (n={len(trec_pairs)})", trec_m)
        _print(f"{name} on Unburden synthetic (n={len(synth_pairs)})", synth_m)
        report[name] = {"trec_test": trec_m, "synthetic": synth_m}

    print("\n=== Head-to-head ===")
    print(f"{'model':14s} {'trec_acc':>8s} {'trec_f1':>8s} {'synth_acc':>9s} {'synth_f1':>8s}")
    for name, block in report.items():
        print(
            f"{name:14s} {block['trec_test']['accuracy']:8.3f} {block['trec_test']['macro_f1']:8.3f} "
            f"{block['synthetic']['accuracy']:9.3f} {block['synthetic']['macro_f1']:8.3f}"
        )

    out = ROOT / "benchmarks" / "trec_finetune_eval_last_run.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"\nWrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

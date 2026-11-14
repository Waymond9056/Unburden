#!/usr/bin/env python3
"""Benchmark zero-shot DeBERTa NLI against the lexical keyword baseline.

Usage (from backend/):

    pip install -r requirements-ml.txt
    python scripts/benchmark_nli.py

Does not change verification decisions. Prints accuracy / per-label metrics and
scores the live seed evidence candidates for side-by-side inspection.
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.services.nli_deberta import (  # noqa: E402
    DEFAULT_MODEL_NAME,
    NliDependenciesMissing,
    lexical_support_label,
    ml_dependencies_available,
    requirement_hypothesis,
    score_passage,
)
from app.services.policy import REQUIREMENTS_BY_ID  # noqa: E402

BENCHMARK_PATH = ROOT / "benchmarks" / "nli_support_benchmark.json"


def _load_benchmark() -> dict:
    return json.loads(BENCHMARK_PATH.read_text(encoding="utf-8"))


def _metrics(y_true: list[str], y_pred: list[str]) -> dict:
    labels = sorted(set(y_true) | set(y_pred))
    correct = sum(a == b for a, b in zip(y_true, y_pred, strict=True))
    accuracy = correct / len(y_true) if y_true else 0.0
    per_label: dict[str, dict[str, float]] = {}
    for label in labels:
        tp = sum(t == label and p == label for t, p in zip(y_true, y_pred, strict=True))
        fp = sum(t != label and p == label for t, p in zip(y_true, y_pred, strict=True))
        fn = sum(t == label and p != label for t, p in zip(y_true, y_pred, strict=True))
        precision = tp / (tp + fp) if (tp + fp) else 0.0
        recall = tp / (tp + fn) if (tp + fn) else 0.0
        f1 = (
            (2 * precision * recall / (precision + recall))
            if (precision + recall)
            else 0.0
        )
        per_label[label] = {
            "precision": precision,
            "recall": recall,
            "f1": f1,
            "support": float(sum(t == label for t in y_true)),
        }
    macro_f1 = (
        sum(item["f1"] for item in per_label.values()) / len(per_label) if per_label else 0.0
    )
    return {
        "accuracy": accuracy,
        "correct": correct,
        "total": len(y_true),
        "macro_f1": macro_f1,
        "per_label": per_label,
    }


def _print_metrics(title: str, metrics: dict) -> None:
    print(f"\n=== {title} ===")
    print(
        f"accuracy={metrics['accuracy']:.3f} "
        f"({metrics['correct']}/{metrics['total']})  macro_f1={metrics['macro_f1']:.3f}"
    )
    for label, row in sorted(metrics["per_label"].items()):
        print(
            f"  {label:13s}  P={row['precision']:.3f}  R={row['recall']:.3f}  "
            f"F1={row['f1']:.3f}  n={int(row['support'])}"
        )


def _tag_slice_accuracy(
    examples: list[dict], preds: list[str], tag: str
) -> tuple[int, int]:
    matched = [
        (ex["gold_label"], pred)
        for ex, pred in zip(examples, preds, strict=True)
        if tag in ex.get("tags", [])
    ]
    if not matched:
        return 0, 0
    correct = sum(gold == pred for gold, pred in matched)
    return correct, len(matched)


def run_labeled_benchmark(*, model_name: str = DEFAULT_MODEL_NAME) -> dict:
    payload = _load_benchmark()
    examples = payload["examples"]
    gold = [item["gold_label"] for item in examples]
    lexical_preds: list[str] = []
    deberta_preds: list[str] = []
    rows: list[dict] = []

    for item in examples:
        requirement = REQUIREMENTS_BY_ID[item["requirement_id"]]
        hypothesis = requirement_hypothesis(requirement)
        lexical = lexical_support_label(item["passage"], requirement)
        lexical_preds.append(lexical)
        score = score_passage(item["passage"], hypothesis, model_name=model_name)
        deberta_preds.append(score.predicted_label)
        rows.append(
            {
                "id": item["id"],
                "requirement_id": item["requirement_id"],
                "gold": item["gold_label"],
                "lexical": lexical,
                "deberta": score.predicted_label,
                "entailment": round(score.entailment, 4),
                "neutral": round(score.neutral, 4),
                "contradiction": round(score.contradiction, 4),
                "tags": item.get("tags", []),
                "agree_lexical": lexical == item["gold_label"],
                "agree_deberta": score.predicted_label == item["gold_label"],
            }
        )

    lexical_metrics = _metrics(gold, lexical_preds)
    deberta_metrics = _metrics(gold, deberta_preds)

    print(f"Benchmark: {BENCHMARK_PATH.name}  n={len(examples)}")
    print(f"Model: {model_name}")
    _print_metrics("Lexical keyword baseline", lexical_metrics)
    _print_metrics("DeBERTa-v3 zero-shot NLI", deberta_metrics)

    print("\n=== Hard-slice accuracy (DeBERTa / Lexical) ===")
    for tag in ("trap", "negation", "misleading", "ambiguous", "seed-like"):
        d_ok, d_n = _tag_slice_accuracy(examples, deberta_preds, tag)
        l_ok, l_n = _tag_slice_accuracy(examples, lexical_preds, tag)
        if d_n == 0 and l_n == 0:
            continue
        print(
            f"  {tag:12s}  deberta={d_ok}/{d_n} ({(d_ok / d_n) if d_n else 0:.3f})  "
            f"lexical={l_ok}/{l_n} ({(l_ok / l_n) if l_n else 0:.3f})"
        )

    disagreements = [
        row
        for row in rows
        if row["agree_deberta"] != row["agree_lexical"] or row["deberta"] != row["lexical"]
    ]
    print(f"\n=== Disagreements / interesting rows ({len(disagreements)}) ===")
    for row in disagreements[:25]:
        mark = "OK" if row["agree_deberta"] else "MISS"
        print(
            f"  [{mark}] {row['id']}: gold={row['gold']}  "
            f"lex={row['lexical']}  deb={row['deberta']}  "
            f"E={row['entailment']:.2f}/N={row['neutral']:.2f}/C={row['contradiction']:.2f}"
        )

    return {
        "lexical": lexical_metrics,
        "deberta": deberta_metrics,
        "rows": rows,
    }


def score_seed_candidates(*, model_name: str = DEFAULT_MODEL_NAME) -> list[dict]:
    """Retrieve candidates from synthetic seed PDFs and score them (no DB writes)."""
    from app.models.db import Document, DocumentPage
    from app.services.evidence_retrieval import retrieve_page_candidates
    from app.services.pdf_extract import extract_pages
    from app.services.policy import REQUIREMENTS
    from app.services.seed import generate_seed_pdfs

    seed_dir = ROOT / "benchmarks" / "_tmp_seed_pdfs"
    specs = generate_seed_pdfs(seed_dir)
    rows: list[dict] = []

    for spec in specs:
        pages = extract_pages(spec["path"])
        document = Document(
            id=f"seed-{spec['filename']}",
            patient_id="benchmark-patient",
            filename=spec["filename"],
            original_filename=spec["filename"],
            document_type=spec["document_type"],
            storage_path=str(spec["path"]),
            page_count=len(pages),
        )
        for raw_page in pages:
            page = DocumentPage(
                document_id=document.id,
                page_number=raw_page["page_number"],
                text=raw_page["text"],
            )
            for requirement in REQUIREMENTS:
                for candidate in retrieve_page_candidates(
                    document=document,
                    page=page,
                    requirement=requirement,
                ):
                    score = score_passage(
                        candidate.supporting_quote,
                        requirement_hypothesis(requirement),
                        model_name=model_name,
                    )
                    lexical = lexical_support_label(
                        candidate.supporting_quote, requirement
                    )
                    rows.append(
                        {
                            "document": spec["filename"],
                            "requirement_id": requirement.id,
                            "quote": candidate.supporting_quote[:160].replace("\n", " "),
                            "lexical": lexical,
                            "deberta": score.predicted_label,
                            "entailment": round(score.entailment, 4),
                            "neutral": round(score.neutral, 4),
                            "contradiction": round(score.contradiction, 4),
                        }
                    )

    print(f"\n=== Seed evidence candidates scored ({len(rows)}) ===")
    by_req: dict[str, int] = Counter(row["requirement_id"] for row in rows)
    print("counts by requirement:", dict(by_req))
    for row in rows:
        print(
            f"  {row['document'][:28]:28s} {row['requirement_id'][:28]:28s} "
            f"lex={row['lexical']:13s} deb={row['deberta']:13s} "
            f"E={row['entailment']:.2f}  | {row['quote'][:90]}..."
        )
    return rows


def main() -> int:
    if not ml_dependencies_available():
        print(
            "Missing ML dependencies. Install with:\n"
            "  pip install -r requirements-ml.txt",
            file=sys.stderr,
        )
        return 1
    try:
        results = run_labeled_benchmark()
        seed_rows = score_seed_candidates()
    except NliDependenciesMissing as exc:
        print(str(exc), file=sys.stderr)
        return 1

    out_path = ROOT / "benchmarks" / "nli_benchmark_last_run.json"
    out_path.write_text(
        json.dumps(
            {
                "model": DEFAULT_MODEL_NAME,
                "labeled": {
                    "lexical": results["lexical"],
                    "deberta": results["deberta"],
                    "rows": results["rows"],
                },
                "seed_candidates": seed_rows,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"\nWrote detailed results → {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

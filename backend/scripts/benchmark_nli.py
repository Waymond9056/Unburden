#!/usr/bin/env python3
"""Compare lexical / DeBERTa / PubMedBERT-MedNLI / ensemble on the NLI benchmark.

Usage (from backend/):

    pip install -r requirements-ml.txt
    python scripts/benchmark_nli.py

Does not change verification decisions.
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.services.nli_deberta import (  # noqa: E402
    BIOMED_MODEL_NAME,
    DEFAULT_MODEL_NAME,
    LABEL_NEUTRAL,
    NliDependenciesMissing,
    lexical_support_label,
    ml_dependencies_available,
    requirement_hypothesis,
    score_passage,
)
from app.services.policy import REQUIREMENTS_BY_ID  # noqa: E402

BENCHMARK_PATH = ROOT / "benchmarks" / "nli_support_benchmark.json"
SYSTEMS = ("lexical", "deberta", "pubmedbert", "ensemble")


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


def run_labeled_benchmark() -> dict:
    payload = _load_benchmark()
    examples = payload["examples"]
    gold = [item["gold_label"] for item in examples]
    preds: dict[str, list[str]] = {name: [] for name in SYSTEMS}
    rows: list[dict] = []
    agree_count = 0

    for item in examples:
        requirement = REQUIREMENTS_BY_ID[item["requirement_id"]]
        hypothesis = requirement_hypothesis(requirement)
        lexical = lexical_support_label(item["passage"], requirement)
        deberta = score_passage(
            item["passage"], hypothesis, model_name=DEFAULT_MODEL_NAME
        )
        biomed = score_passage(
            item["passage"], hypothesis, model_name=BIOMED_MODEL_NAME
        )
        agreed = deberta.predicted_label == biomed.predicted_label
        ensemble_label = deberta.predicted_label if agreed else LABEL_NEUTRAL
        if agreed:
            agree_count += 1

        preds["lexical"].append(lexical)
        preds["deberta"].append(deberta.predicted_label)
        preds["pubmedbert"].append(biomed.predicted_label)
        preds["ensemble"].append(ensemble_label)

        rows.append(
            {
                "id": item["id"],
                "requirement_id": item["requirement_id"],
                "gold": item["gold_label"],
                "lexical": lexical,
                "deberta": deberta.predicted_label,
                "pubmedbert": biomed.predicted_label,
                "ensemble": ensemble_label,
                "ensemble_agreed": agreed,
                "deberta_scores": {
                    "E": round(deberta.entailment, 4),
                    "N": round(deberta.neutral, 4),
                    "C": round(deberta.contradiction, 4),
                },
                "pubmedbert_scores": {
                    "E": round(biomed.entailment, 4),
                    "N": round(biomed.neutral, 4),
                    "C": round(biomed.contradiction, 4),
                },
                "tags": item.get("tags", []),
            }
        )

    metrics = {name: _metrics(gold, preds[name]) for name in SYSTEMS}

    print(f"Benchmark: {BENCHMARK_PATH.name}  n={len(examples)}")
    print(f"DeBERTa:     {DEFAULT_MODEL_NAME}")
    print(f"PubMedBERT:  {BIOMED_MODEL_NAME}")
    print(
        f"Ensemble:    agree→label, disagree→neutral "
        f"(agreement={agree_count}/{len(examples)} = {agree_count / len(examples):.3f})"
    )

    _print_metrics("1) Lexical keyword baseline", metrics["lexical"])
    _print_metrics("2) DeBERTa-v3 zero-shot NLI", metrics["deberta"])
    _print_metrics("3) PubMedBERT-MNLI-MedNLI", metrics["pubmedbert"])
    _print_metrics("4) Ensemble (DeBERTa + PubMedBERT)", metrics["ensemble"])

    print("\n=== Head-to-head summary ===")
    print(
        f"{'system':12s}  {'acc':>6s}  {'macroF1':>8s}  "
        f"{'entP':>6s}  {'entR':>6s}  {'conP':>6s}  {'conR':>6s}"
    )
    for name in SYSTEMS:
        m = metrics[name]
        ent = m["per_label"].get("entailment", {})
        con = m["per_label"].get("contradiction", {})
        print(
            f"{name:12s}  {m['accuracy']:6.3f}  {m['macro_f1']:8.3f}  "
            f"{ent.get('precision', 0):6.3f}  {ent.get('recall', 0):6.3f}  "
            f"{con.get('precision', 0):6.3f}  {con.get('recall', 0):6.3f}"
        )

    print("\n=== Hard-slice accuracy ===")
    for tag in ("trap", "negation", "misleading", "ambiguous", "seed-like"):
        parts = []
        for name in SYSTEMS:
            ok, n = _tag_slice_accuracy(examples, preds[name], tag)
            if n == 0:
                continue
            parts.append(f"{name}={ok}/{n} ({ok / n:.3f})")
        if parts:
            print(f"  {tag:12s}  " + "  ".join(parts))

    interesting = [
        row
        for row in rows
        if len({row["lexical"], row["deberta"], row["pubmedbert"], row["ensemble"]}) > 1
        or not row["ensemble_agreed"]
    ]
    print(f"\n=== Disagreements / interesting rows ({len(interesting)}) ===")
    for row in interesting[:30]:
        mark = "OK" if row["ensemble"] == row["gold"] else "MISS"
        print(
            f"  [{mark}] {row['id']}: gold={row['gold']}  "
            f"lex={row['lexical']} deb={row['deberta']} "
            f"pub={row['pubmedbert']} ens={row['ensemble']}"
            f"{'' if row['ensemble_agreed'] else ' [DISAGREE→neutral]'}"
        )

    return {
        "metrics": metrics,
        "preds": preds,
        "rows": rows,
        "agreement_rate": agree_count / len(examples) if examples else 0.0,
    }


def score_seed_candidates() -> list[dict]:
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
                    hypothesis = requirement_hypothesis(requirement)
                    lexical = lexical_support_label(
                        candidate.supporting_quote, requirement
                    )
                    deberta = score_passage(
                        candidate.supporting_quote,
                        hypothesis,
                        model_name=DEFAULT_MODEL_NAME,
                    )
                    biomed = score_passage(
                        candidate.supporting_quote,
                        hypothesis,
                        model_name=BIOMED_MODEL_NAME,
                    )
                    agreed = deberta.predicted_label == biomed.predicted_label
                    ensemble_label = (
                        deberta.predicted_label if agreed else LABEL_NEUTRAL
                    )
                    rows.append(
                        {
                            "document": spec["filename"],
                            "requirement_id": requirement.id,
                            "quote": candidate.supporting_quote[:160].replace("\n", " "),
                            "lexical": lexical,
                            "deberta": deberta.predicted_label,
                            "pubmedbert": biomed.predicted_label,
                            "ensemble": ensemble_label,
                            "ensemble_agreed": agreed,
                            "deberta_E": round(deberta.entailment, 4),
                            "pubmedbert_E": round(biomed.entailment, 4),
                        }
                    )

    print(f"\n=== Seed evidence candidates scored ({len(rows)}) ===")
    print("counts by requirement:", dict(Counter(row["requirement_id"] for row in rows)))
    for row in rows:
        print(
            f"  {row['document'][:26]:26s} {row['requirement_id'][:24]:24s} "
            f"lex={row['lexical'][:1]} deb={row['deberta'][:1]} "
            f"pub={row['pubmedbert'][:1]} ens={row['ensemble'][:1]}"
            f"{'' if row['ensemble_agreed'] else '*'}  "
            f"Edeb={row['deberta_E']:.2f} Epub={row['pubmedbert_E']:.2f}  "
            f"| {row['quote'][:70]}..."
        )
    print("  legend: e/n/c = entailment/neutral/contradiction; * = models disagreed")
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
                "models": {
                    "deberta": DEFAULT_MODEL_NAME,
                    "pubmedbert": BIOMED_MODEL_NAME,
                    "ensemble": "agree→label, disagree→neutral",
                },
                "labeled": {
                    "metrics": results["metrics"],
                    "agreement_rate": results["agreement_rate"],
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

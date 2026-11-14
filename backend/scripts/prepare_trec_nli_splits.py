#!/usr/bin/env python3
"""Download TREC-CT via NLI4PR and write Unburden-style NLI train/val/test splits.

Source: Hugging Face `Mathilde/NLI4PR` (TREC Clinical Trials 2022 eligibility
judgments mapped to Entailment/Contradiction).

We convert to Unburden's premise/hypothesis convention:
  premise  = patient note (statement_medical)
  hypothesis = trial eligibility criteria text (premise field in NLI4PR)
  label    = entailment | contradiction | neutral

Neutral examples are injected from Unburden's synthetic NLI benchmark so the
3-way DeBERTa head stays intact (NLI4PR is 2-class only).

Usage (from backend/):
  python scripts/prepare_trec_nli_splits.py
"""

from __future__ import annotations

import json
import random
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

OUT_DIR = ROOT / "benchmarks" / "trec_nli"
SYNTHETIC_PATH = ROOT / "benchmarks" / "nli_support_benchmark.json"
SEED = 42

LABEL_MAP = {
    "Entailment": "entailment",
    "Contradiction": "contradiction",
    "entailment": "entailment",
    "contradiction": "contradiction",
    "neutral": "neutral",
}


def _truncate(text: str, max_chars: int = 1800) -> str:
    text = " ".join((text or "").split())
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 3].rstrip() + "..."


def _from_nli4pr(split_name: str, rows) -> list[dict]:
    out: list[dict] = []
    for row in rows:
        label = LABEL_MAP.get(row["label"])
        if label is None:
            continue
        out.append(
            {
                "id": f"trec-{split_name}-{row['id']}",
                "source": "nli4pr-trec-ct-2022",
                "topic_id": str(row.get("topic_id", "")),
                "nct_id": row.get("NCT_id", ""),
                "premise": _truncate(row["statement_medical"]),
                "hypothesis": _truncate(row["premise"]),
                "label": label,
                "split": split_name,
            }
        )
    return out


def _synthetic_neutrals(split: str, rng: random.Random) -> list[dict]:
    payload = json.loads(SYNTHETIC_PATH.read_text(encoding="utf-8"))
    neutrals = [ex for ex in payload["examples"] if ex["gold_label"] == "neutral"]
    # Also include a few contradiction/entailment synthetics in train only for domain mix.
    extras = [ex for ex in payload["examples"] if ex["gold_label"] != "neutral"]
    from app.services.nli_deberta import requirement_hypothesis
    from app.services.policy import REQUIREMENTS_BY_ID

    def _row(ex: dict, idx: int) -> dict:
        requirement = REQUIREMENTS_BY_ID[ex["requirement_id"]]
        return {
            "id": f"synthetic-{split}-{ex['id']}-{idx}",
            "source": "unburden-synthetic",
            "topic_id": "",
            "nct_id": "",
            "premise": _truncate(ex["passage"]),
            "hypothesis": requirement_hypothesis(requirement),
            "label": ex["gold_label"],
            "split": split,
        }

    if split == "train":
        chosen_n = neutrals
        chosen_x = extras
    elif split == "validation":
        chosen_n = neutrals[: max(1, len(neutrals) // 2)]
        chosen_x = []
    else:  # keep Unburden synthetic held out of TREC test; use all neutrals in a side eval
        chosen_n = []
        chosen_x = []

    rows = [_row(ex, i) for i, ex in enumerate(chosen_n)]
    rows.extend(_row(ex, i) for i, ex in enumerate(chosen_x))
    rng.shuffle(rows)
    return rows


def main() -> int:
    from datasets import load_dataset

    rng = random.Random(SEED)
    print("Loading Mathilde/NLI4PR (TREC Clinical Trials → NLI)...")
    ds = load_dataset("Mathilde/NLI4PR")

    splits = {
        "train": _from_nli4pr("train", ds["train"]) + _synthetic_neutrals("train", rng),
        "validation": _from_nli4pr("validation", ds["validation"])
        + _synthetic_neutrals("validation", rng),
        "test": _from_nli4pr("test", ds["test"]),
    }
    for name, rows in splits.items():
        rng.shuffle(rows)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    meta = {
        "seed": SEED,
        "source_primary": "Mathilde/NLI4PR (TREC Clinical Trials 2022)",
        "label_mapping": {
            "eligible": "entailment",
            "excluded": "contradiction",
            "synthetic_unrelated_or_insufficient": "neutral",
        },
        "counts": {name: dict(Counter(r["label"] for r in rows)) for name, rows in splits.items()},
        "totals": {name: len(rows) for name, rows in splits.items()},
        "notes": [
            "premise=patient note, hypothesis=trial eligibility criteria text",
            "Matches Unburden NLI direction: does the clinical passage support the requirement?",
            "NLI4PR has no neutral class; Unburden synthetic neutrals are mixed into train/val only.",
            "TREC test split is held out pure (no synthetic leakage).",
        ],
    }
    (OUT_DIR / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    for name, rows in splits.items():
        path = OUT_DIR / f"{name}.jsonl"
        with path.open("w", encoding="utf-8") as handle:
            for row in rows:
                handle.write(json.dumps(row, ensure_ascii=False) + "\n")
        print(f"Wrote {path}  n={len(rows)}  {meta['counts'][name]}")

    print(f"\nMeta → {OUT_DIR / 'meta.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

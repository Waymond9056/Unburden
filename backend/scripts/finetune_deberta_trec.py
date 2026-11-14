#!/usr/bin/env python3
"""Fine-tune DeBERTa-v3 NLI on TREC Clinical Trials (NLI4PR) splits.

Usage (from backend/):
  python scripts/prepare_trec_nli_splits.py
  python scripts/finetune_deberta_trec.py
  python scripts/finetune_deberta_trec.py --max-train-samples 800 --epochs 1   # faster smoke

Writes checkpoint to backend/models/deberta-trec-nli/
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

DEFAULT_BASE = "MoritzLaurer/DeBERTa-v3-base-mnli-fever-anli"
DATA_DIR = ROOT / "benchmarks" / "trec_nli"
OUT_DIR = ROOT / "models" / "deberta-trec-nli"

LABEL2ID = {"entailment": 0, "neutral": 1, "contradiction": 2}
ID2LABEL = {0: "entailment", 1: "neutral", 2: "contradiction"}


def _load_jsonl(path: Path) -> list[dict]:
    rows = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-model", default=DEFAULT_BASE)
    parser.add_argument("--output-dir", type=Path, default=OUT_DIR)
    parser.add_argument("--epochs", type=float, default=1.0)
    parser.add_argument("--batch-size", type=int, default=4)
    parser.add_argument("--lr", type=float, default=2e-5)
    parser.add_argument("--max-length", type=int, default=256)
    parser.add_argument("--max-train-samples", type=int, default=0)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    train_path = DATA_DIR / "train.jsonl"
    val_path = DATA_DIR / "validation.jsonl"
    if not train_path.exists():
        print("Missing splits. Run: python scripts/prepare_trec_nli_splits.py", file=sys.stderr)
        return 1

    import numpy as np
    import torch
    from datasets import Dataset
    from sklearn.metrics import accuracy_score, f1_score
    from transformers import (
        AutoModelForSequenceClassification,
        AutoTokenizer,
        Trainer,
        TrainingArguments,
        set_seed,
    )

    set_seed(args.seed)
    train_rows = _load_jsonl(train_path)
    val_rows = _load_jsonl(val_path)
    if args.max_train_samples and args.max_train_samples < len(train_rows):
        rng = np.random.default_rng(args.seed)
        idx = rng.choice(len(train_rows), size=args.max_train_samples, replace=False)
        train_rows = [train_rows[i] for i in sorted(idx.tolist())]

    print(f"Train n={len(train_rows)}  Val n={len(val_rows)}")
    print(f"Base model: {args.base_model}")

    tokenizer = AutoTokenizer.from_pretrained(args.base_model)
    model = AutoModelForSequenceClassification.from_pretrained(
        args.base_model,
        num_labels=3,
        id2label=ID2LABEL,
        label2id=LABEL2ID,
        ignore_mismatched_sizes=False,
    )

    def _tokenize_batch(batch: dict) -> dict:
        enc = tokenizer(
            batch["premise"],
            batch["hypothesis"],
            truncation=True,
            max_length=args.max_length,
            padding=False,
        )
        enc["labels"] = [LABEL2ID[label] for label in batch["label"]]
        return enc

    train_ds = Dataset.from_list(train_rows).map(
        _tokenize_batch, batched=True, remove_columns=list(train_rows[0].keys())
    )
    val_ds = Dataset.from_list(val_rows).map(
        _tokenize_batch, batched=True, remove_columns=list(val_rows[0].keys())
    )

    def _compute_metrics(eval_pred):
        logits, labels = eval_pred
        preds = np.argmax(logits, axis=-1)
        return {
            "accuracy": float(accuracy_score(labels, preds)),
            "macro_f1": float(f1_score(labels, preds, average="macro")),
        }

    use_mps = torch.backends.mps.is_available()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    training_args = TrainingArguments(
        output_dir=str(args.output_dir / "runs"),
        learning_rate=args.lr,
        per_device_train_batch_size=args.batch_size,
        per_device_eval_batch_size=args.batch_size,
        num_train_epochs=args.epochs,
        eval_strategy="epoch",
        save_strategy="epoch",
        load_best_model_at_end=True,
        metric_for_best_model="macro_f1",
        greater_is_better=True,
        logging_steps=50,
        seed=args.seed,
        report_to=[],
        fp16=False,
        use_cpu=not use_mps and not torch.cuda.is_available(),
    )

    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=train_ds,
        eval_dataset=val_ds,
        processing_class=tokenizer,
        compute_metrics=_compute_metrics,
    )
    trainer.train()
    metrics = trainer.evaluate()
    print("Validation:", metrics)

    trainer.save_model(str(args.output_dir))
    tokenizer.save_pretrained(str(args.output_dir))
    (args.output_dir / "finetune_meta.json").write_text(
        json.dumps(
            {
                "base_model": args.base_model,
                "train_size": len(train_rows),
                "val_size": len(val_rows),
                "epochs": args.epochs,
                "max_length": args.max_length,
                "validation_metrics": {k: float(v) for k, v in metrics.items() if isinstance(v, (int, float))},
                "label2id": LABEL2ID,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"Saved fine-tuned model → {args.output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

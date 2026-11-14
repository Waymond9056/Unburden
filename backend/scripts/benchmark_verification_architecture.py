#!/usr/bin/env python3
"""Compare Milestone 3 alone vs Milestone 3 + DeBERTa precision/negation signal.

Usage (from backend/):

    USE_NLI_SUPPORT is forced per-call via verify_candidate(use_nli=...).
    python scripts/benchmark_verification_architecture.py
"""

from __future__ import annotations

import json
import sys
import uuid
from datetime import date
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.core.database import Base  # noqa: E402
from app.models.db import Document, DocumentPage, EvidenceCandidate, Patient  # noqa: E402
from app.services.evidence_verification import verify_candidate  # noqa: E402
from app.services.nli_deberta import ml_dependencies_available  # noqa: E402
from app.services.policy import REQUIREMENTS_BY_ID  # noqa: E402

BENCHMARK_PATH = ROOT / "benchmarks" / "verification_architecture_benchmark.json"


def _session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine, autocommit=False, autoflush=False)()


def _build_candidate(db, case: dict) -> EvidenceCandidate:
    doc_id = f"doc-{case['id']}"
    page = 1
    patient_id = "arch-bench-patient"
    if db.get(Patient, patient_id) is None:
        db.add(Patient(id=patient_id, display_name="Arch Bench", date_of_birth=date(1985, 3, 12)))
    db.add(
        Document(
            id=doc_id,
            patient_id=patient_id,
            filename=f"{case['id']}.pdf",
            original_filename=f"{case['id']}.pdf",
            document_type=case["document_type"],
            storage_path=f"/tmp/{case['id']}.pdf",
            page_count=1,
        )
    )
    db.add(DocumentPage(document_id=doc_id, page_number=page, text=case["quote"]))
    candidate = EvidenceCandidate(
        id=str(uuid.uuid4()),
        patient_id=patient_id,
        document_id=doc_id,
        policy_id="fictional-severe-asthma-policy",
        requirement_id=case["requirement_id"],
        source_page=page,
        supporting_quote=case["quote"],
        extracted_details_json="{}",
        relevance_score=0.9,
        retrieval_method="lexical",
        verification_status="unverified_candidate",
    )
    db.add(candidate)
    db.commit()
    candidate.document = db.get(Document, doc_id)
    return candidate


def main() -> int:
    if not ml_dependencies_available():
        print("Install ML deps first: pip install -r requirements-ml.txt", file=sys.stderr)
        return 1

    payload = json.loads(BENCHMARK_PATH.read_text(encoding="utf-8"))
    as_of = date.fromisoformat(payload["as_of_date"])
    rows: list[dict] = []

    for case in payload["cases"]:
        db = _session()
        candidate = _build_candidate(db, case)
        requirement = REQUIREMENTS_BY_ID[case["requirement_id"]]
        m3 = verify_candidate(
            db, candidate, requirement, as_of_date=as_of, use_nli=False
        )
        combo = verify_candidate(
            db, candidate, requirement, as_of_date=as_of, use_nli=True
        )
        rows.append(
            {
                "id": case["id"],
                "requirement_id": case["requirement_id"],
                "gold": case["gold_status"],
                "m3_only": m3.status,
                "m3_deberta": combo.status,
                "m3_ok": m3.status == case["gold_status"],
                "combo_ok": combo.status == case["gold_status"],
                "m3_reasons": m3.reasons,
                "combo_reasons": combo.reasons,
                "tags": case.get("tags", []),
            }
        )

    n = len(rows)
    m3_correct = sum(1 for row in rows if row["m3_ok"])
    combo_correct = sum(1 for row in rows if row["combo_ok"])
    m3_acc = m3_correct / n if n else 0.0
    combo_acc = combo_correct / n if n else 0.0

    print(f"Architecture benchmark: {BENCHMARK_PATH.name}  n={n}")
    print(
        f"Milestone 3 only:           accuracy={m3_acc:.3f} ({m3_correct}/{n})"
    )
    print(
        f"Milestone 3 + DeBERTa:      accuracy={combo_acc:.3f} ({combo_correct}/{n})"
    )
    print(
        f"Delta (combo - m3):         {combo_acc - m3_acc:+.3f} "
        f"({combo_correct - m3_correct:+d} cases)"
    )

    nli_targets = [row for row in rows if "nli-target" in row["tags"]]
    if nli_targets:
        m3_n = sum(1 for row in nli_targets if row["m3_ok"])
        c_n = sum(1 for row in nli_targets if row["combo_ok"])
        print(
            f"\nNegation / NLI-target slice (n={len(nli_targets)}): "
            f"m3={m3_n}/{len(nli_targets)}  combo={c_n}/{len(nli_targets)}"
        )

    print("\n=== Case detail ===")
    for row in rows:
        marker = " "
        if row["m3_ok"] != row["combo_ok"]:
            marker = "*"
        print(
            f"  {marker} {row['id']}: gold={row['gold']:12s}  "
            f"m3={row['m3_only']:12s}  combo={row['m3_deberta']:12s}"
        )
        if not row["combo_ok"] or (row["m3_ok"] != row["combo_ok"]):
            print(f"      m3:    {row['m3_reasons'][0][:90]}")
            print(f"      combo: {row['combo_reasons'][0][:90]}")

    out = ROOT / "benchmarks" / "verification_architecture_last_run.json"
    out.write_text(json.dumps({"rows": rows, "m3_acc": m3_acc, "combo_acc": combo_acc}, indent=2))
    print(f"\nWrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

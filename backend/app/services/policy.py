from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Any


POLICY_DIR = Path(__file__).resolve().parents[1] / "policies"
FICTIONAL_POLICY_ID = "fictional-severe-asthma-policy"


@dataclass(frozen=True)
class TemporalConstraint:
    within_months: int
    date_required: bool = True


@dataclass(frozen=True)
class NumericConstraint:
    min_value: float
    unit_substring: str


@dataclass(frozen=True)
class RequirementDefinition:
    id: str
    title: str
    description: str
    retrieval_terms: tuple[str, ...]
    detail_fields: tuple[str, ...]
    acceptable_document_types: tuple[str, ...]
    must_match_any: tuple[str, ...]
    reject_if_quote_matches_any: tuple[str, ...]
    ambiguous_if_quote_matches_any: tuple[str, ...]
    temporal: TemporalConstraint | None
    numeric: NumericConstraint | None
    min_accepted_candidates: int
    suggested_document_types: tuple[str, ...]
    require_interval_days_min: int | None = None
    policy_id: str = FICTIONAL_POLICY_ID


@dataclass(frozen=True)
class PolicyDefinition:
    id: str
    name: str
    disclaimer: str
    logic: str
    as_of_date: date
    requirements: tuple[RequirementDefinition, ...]


def _parse_requirement(raw: dict[str, Any], policy_id: str) -> RequirementDefinition:
    temporal_raw = raw.get("temporal")
    numeric_raw = raw.get("numeric")
    return RequirementDefinition(
        id=raw["id"],
        title=raw["title"],
        description=raw["description"],
        retrieval_terms=tuple(raw.get("retrieval_terms", [])),
        detail_fields=tuple(raw.get("detail_fields", [])),
        acceptable_document_types=tuple(raw.get("acceptable_document_types", [])),
        must_match_any=tuple(raw.get("must_match_any", [])),
        reject_if_quote_matches_any=tuple(raw.get("reject_if_quote_matches_any", [])),
        ambiguous_if_quote_matches_any=tuple(raw.get("ambiguous_if_quote_matches_any", [])),
        temporal=(
            TemporalConstraint(
                within_months=int(temporal_raw["within_months"]),
                date_required=bool(temporal_raw.get("date_required", True)),
            )
            if temporal_raw
            else None
        ),
        numeric=(
            NumericConstraint(
                min_value=float(numeric_raw["min_value"]),
                unit_substring=str(numeric_raw["unit_substring"]),
            )
            if numeric_raw
            else None
        ),
        min_accepted_candidates=int(raw.get("min_accepted_candidates", 1)),
        suggested_document_types=tuple(raw.get("suggested_document_types", [])),
        require_interval_days_min=(
            int(raw["require_interval_days_min"])
            if raw.get("require_interval_days_min") is not None
            else None
        ),
        policy_id=policy_id,
    )


@lru_cache
def load_policy(policy_id: str = FICTIONAL_POLICY_ID) -> PolicyDefinition:
    path = POLICY_DIR / "fictional_severe_asthma_pa.json"
    if policy_id != FICTIONAL_POLICY_ID:
        raise KeyError(f"Unknown policy: {policy_id}")
    raw = json.loads(path.read_text(encoding="utf-8"))
    requirements = tuple(_parse_requirement(item, raw["id"]) for item in raw["requirements"])
    return PolicyDefinition(
        id=raw["id"],
        name=raw["name"],
        disclaimer=raw["disclaimer"],
        logic=raw.get("logic", "AND"),
        as_of_date=date.fromisoformat(raw["as_of_date"]),
        requirements=requirements,
    )


def get_requirements(policy_id: str = FICTIONAL_POLICY_ID) -> tuple[RequirementDefinition, ...]:
    return load_policy(policy_id).requirements


POLICY = load_policy()
REQUIREMENTS = POLICY.requirements
REQUIREMENTS_BY_ID = {requirement.id: requirement for requirement in REQUIREMENTS}

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Any


POLICY_DIR = Path(__file__).resolve().parents[1] / "policies"
FICTIONAL_POLICY_ID = "fictional-severe-asthma-policy"
SIMPLE_ASTHMA_POLICY_ID = "simple-asthma-insurance"

POLICY_FILES: dict[str, str] = {
    FICTIONAL_POLICY_ID: "fictional_severe_asthma_pa.json",
    SIMPLE_ASTHMA_POLICY_ID: "simple_asthma_insurance.json",
}


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
    min_support_candidates: int
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
        min_support_candidates=int(
            raw.get("min_support_candidates", raw.get("min_accepted_candidates", 1))
        ),
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
    filename = POLICY_FILES.get(policy_id)
    if filename is None:
        raise KeyError(f"Unknown policy: {policy_id}")
    path = POLICY_DIR / filename
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


def list_policy_ids() -> tuple[str, ...]:
    return tuple(POLICY_FILES.keys())


def list_policies() -> tuple[PolicyDefinition, ...]:
    return tuple(load_policy(policy_id) for policy_id in list_policy_ids())


def get_requirements(policy_id: str = FICTIONAL_POLICY_ID) -> tuple[RequirementDefinition, ...]:
    return load_policy(policy_id).requirements


def known_policy_id(policy_id: str) -> bool:
    return policy_id in POLICY_FILES


POLICY = load_policy()
REQUIREMENTS = POLICY.requirements
# Union across insurers so shared requirement ids (e.g. diagnosis) resolve.
REQUIREMENTS_BY_ID: dict[str, RequirementDefinition] = {}
for _policy in list_policies():
    for _requirement in _policy.requirements:
        REQUIREMENTS_BY_ID.setdefault(_requirement.id, _requirement)

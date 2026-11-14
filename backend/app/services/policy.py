from __future__ import annotations

from dataclasses import dataclass


FICTIONAL_POLICY_ID = "fictional-severe-asthma-policy"


@dataclass(frozen=True)
class RequirementDefinition:
    id: str
    title: str
    description: str
    retrieval_terms: tuple[str, ...]
    detail_fields: tuple[str, ...]
    policy_id: str = FICTIONAL_POLICY_ID


REQUIREMENTS = (
    RequirementDefinition(
        id="documented_severe_asthma",
        title="Documented severe asthma diagnosis",
        description="Locate passages that may document a severe asthma diagnosis.",
        retrieval_terms=("severe persistent asthma", "severe asthma", "J45.50"),
        detail_fields=("dates", "matched_terms"),
    ),
    RequirementDefinition(
        id="prior_controller_therapy",
        title="Prior high-dose controller therapy",
        description=(
            "Locate passages about an inhaled corticosteroid/controller trial, dose, "
            "and treatment interval."
        ),
        retrieval_terms=(
            "inhaled corticosteroid",
            "long-acting beta agonist",
            "fluticasone-salmeterol",
            "controller therapy",
            "Symbicort",
        ),
        detail_fields=("dates", "dose_mentions", "matched_terms"),
    ),
    RequirementDefinition(
        id="qualifying_eosinophil_result",
        title="Qualifying eosinophil laboratory result",
        description="Locate dated, quantitative eosinophil laboratory passages.",
        retrieval_terms=("eosinophil", "cells/µL", "cells/uL"),
        detail_fields=("dates", "numeric_mentions", "matched_terms"),
    ),
    RequirementDefinition(
        id="recent_exacerbation_history",
        title="Recent treated asthma exacerbation",
        description=(
            "Locate passages about an asthma exacerbation treated with systemic "
            "corticosteroids or emergency care."
        ),
        retrieval_terms=(
            "exacerbation",
            "systemic corticosteroid",
            "prednisone burst",
            "emergency department",
        ),
        detail_fields=("dates", "matched_terms"),
    ),
)

REQUIREMENTS_BY_ID = {requirement.id: requirement for requirement in REQUIREMENTS}

from fastapi import APIRouter, HTTPException

from app.models.schemas import PolicyRequirementOut
from app.services.policy import FICTIONAL_POLICY_ID, REQUIREMENTS

router = APIRouter(prefix="/policies", tags=["policies"])


@router.get("/{policy_id}/requirements", response_model=list[PolicyRequirementOut])
def list_policy_requirements(policy_id: str) -> list[PolicyRequirementOut]:
    if policy_id != FICTIONAL_POLICY_ID:
        raise HTTPException(status_code=404, detail="Policy not found")
    return [
        PolicyRequirementOut(
            id=requirement.id,
            policy_id=requirement.policy_id,
            title=requirement.title,
            description=requirement.description,
        )
        for requirement in REQUIREMENTS
    ]

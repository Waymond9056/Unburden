from fastapi import APIRouter, HTTPException

from app.models.schemas import PolicyOut, PolicyRequirementOut
from app.services.policy import FICTIONAL_POLICY_ID, load_policy

router = APIRouter(prefix="/policies", tags=["policies"])


@router.get("/{policy_id}", response_model=PolicyOut)
def get_policy(policy_id: str) -> PolicyOut:
    try:
        policy = load_policy(policy_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Policy not found") from exc
    return PolicyOut(
        id=policy.id,
        name=policy.name,
        disclaimer=policy.disclaimer,
        logic=policy.logic,
        as_of_date=policy.as_of_date,
        requirements=[
            PolicyRequirementOut(
                id=requirement.id,
                policy_id=requirement.policy_id,
                title=requirement.title,
                description=requirement.description,
            )
            for requirement in policy.requirements
        ],
    )


@router.get("/{policy_id}/requirements", response_model=list[PolicyRequirementOut])
def list_policy_requirements(policy_id: str) -> list[PolicyRequirementOut]:
    try:
        policy = load_policy(policy_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Policy not found") from exc
    return [
        PolicyRequirementOut(
            id=requirement.id,
            policy_id=requirement.policy_id,
            title=requirement.title,
            description=requirement.description,
        )
        for requirement in policy.requirements
    ]


@router.get("", response_model=list[PolicyOut])
def list_policies() -> list[PolicyOut]:
    policy = load_policy(FICTIONAL_POLICY_ID)
    return [
        PolicyOut(
            id=policy.id,
            name=policy.name,
            disclaimer=policy.disclaimer,
            logic=policy.logic,
            as_of_date=policy.as_of_date,
            requirements=[
                PolicyRequirementOut(
                    id=requirement.id,
                    policy_id=requirement.policy_id,
                    title=requirement.title,
                    description=requirement.description,
                )
                for requirement in policy.requirements
            ],
        )
    ]

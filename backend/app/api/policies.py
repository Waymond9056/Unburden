from fastapi import APIRouter, HTTPException

from app.models.schemas import PolicyOut, PolicyRequirementOut
from app.services.policy import list_policies as load_all_policies, load_policy

router = APIRouter(prefix="/policies", tags=["policies"])


def _policy_out(policy) -> PolicyOut:
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


@router.get("", response_model=list[PolicyOut])
def list_policies() -> list[PolicyOut]:
    return [_policy_out(policy) for policy in load_all_policies()]


@router.get("/{policy_id}", response_model=PolicyOut)
def get_policy(policy_id: str) -> PolicyOut:
    try:
        policy = load_policy(policy_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Policy not found") from exc
    return _policy_out(policy)


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

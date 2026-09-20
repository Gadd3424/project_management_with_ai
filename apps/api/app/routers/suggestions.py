from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select

from ..ai_service import generate_suggestions
from ..audit import add_audit
from ..dependencies import Csrf, CurrentUser, DbSession, Tenant
from ..domain.permissions import OrganizationPermission
from ..models import AISuggestion, AISuggestionFeedback, Project, Task
from ..rate_limit import limit_suggestion_generation
from ..schemas import FeedbackCreate, SuggestionDecision, SuggestionRead, TaskRead
from ..services.authorization_service import AuthorizationService
from .tasks import tenant_task

router = APIRouter(tags=["ai-suggestions"])


async def tenant_suggestion(suggestion_id: str, db: DbSession, tenant: Tenant) -> AISuggestion:
    item = await db.scalar(
        select(AISuggestion)
        .join(Project, AISuggestion.project_id == Project.id)
        .where(
            AISuggestion.id == suggestion_id,
            AISuggestion.organization_id == tenant.organization_id,
            AISuggestion.deleted_at.is_(None),
            Project.organization_id == tenant.organization_id,
            Project.deleted_at.is_(None),
        )
    )
    if not item:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Suggestion not found")
    return item


@router.get("/tasks/{task_id}/suggestions", response_model=list[SuggestionRead])
async def list_suggestions(task_id: str, db: DbSession, tenant: Tenant) -> list[AISuggestion]:
    await tenant_task(task_id, db, tenant)
    return list(
        (
            await db.scalars(
                select(AISuggestion)
                .where(
                    AISuggestion.task_id == task_id,
                    AISuggestion.organization_id == tenant.organization_id,
                    AISuggestion.deleted_at.is_(None),
                )
                .order_by(AISuggestion.created_at.desc())
            )
        ).all()
    )


@router.post("/tasks/{task_id}/suggestions/generate", response_model=list[SuggestionRead], status_code=201)
async def create_suggestions(
    task_id: str,
    request: Request,
    db: DbSession,
    user: CurrentUser,
    tenant: Tenant,
    _: Csrf,
    _rate_limit: None = Depends(limit_suggestion_generation),
) -> list[AISuggestion]:
    await AuthorizationService(db).require_permission(
        user, tenant.organization_id, OrganizationPermission.PROJECTS_AI_SUGGEST
    )
    task = await tenant_task(task_id, db, tenant)
    suggestions = await generate_suggestions(db, task)
    for item in suggestions:
        add_audit(db, request, tenant.organization_id, user, "suggestion.generate", "ai_suggestion", item.id)
    await db.commit()
    for item in suggestions:
        await db.refresh(item)
    return suggestions


async def decide(
    suggestion_id: str,
    decision: str,
    payload: SuggestionDecision,
    request: Request,
    db: DbSession,
    user: CurrentUser,
    tenant: Tenant,
) -> AISuggestion:
    await AuthorizationService(db).require_permission(
        user, tenant.organization_id, OrganizationPermission.PROJECTS_AI_SUGGEST
    )
    item = await tenant_suggestion(suggestion_id, db, tenant)
    if item.decision != "pending":
        raise HTTPException(status.HTTP_409_CONFLICT, "Suggestion already decided")
    item.decision = decision
    item.revised_content = payload.revised_content
    item.version += 1
    add_audit(db, request, tenant.organization_id, user, f"suggestion.{decision}", "ai_suggestion", item.id)
    await db.commit()
    await db.refresh(item)
    return item


@router.post("/suggestions/{suggestion_id}/accept", response_model=SuggestionRead)
async def accept_suggestion(
    suggestion_id: str,
    payload: SuggestionDecision,
    request: Request,
    db: DbSession,
    user: CurrentUser,
    tenant: Tenant,
    _: Csrf,
) -> AISuggestion:
    return await decide(suggestion_id, "accepted", payload, request, db, user, tenant)


@router.post("/suggestions/{suggestion_id}/reject", response_model=SuggestionRead)
async def reject_suggestion(
    suggestion_id: str,
    payload: SuggestionDecision,
    request: Request,
    db: DbSession,
    user: CurrentUser,
    tenant: Tenant,
    _: Csrf,
) -> AISuggestion:
    return await decide(suggestion_id, "rejected", payload, request, db, user, tenant)


@router.get("/suggestions/{suggestion_id}/diff")
async def suggestion_diff(suggestion_id: str, db: DbSession, tenant: Tenant) -> dict:
    item = await tenant_suggestion(suggestion_id, db, tenant)
    task = await tenant_task(item.task_id, db, tenant)
    patch = (item.revised_content or item.content).get("proposed_patch", {})
    after = {"description": task.description + patch.get("description_append", "")}
    return {
        "task_id": task.id,
        "before": {"description": task.description},
        "after": after,
        "task_version": task.version,
    }


@router.post("/suggestions/{suggestion_id}/apply", response_model=TaskRead)
async def apply_suggestion(
    suggestion_id: str,
    request: Request,
    db: DbSession,
    user: CurrentUser,
    tenant: Tenant,
    _: Csrf,
) -> Task:
    await AuthorizationService(db).require_permission(
        user, tenant.organization_id, OrganizationPermission.PROJECTS_AI_SUGGEST
    )
    item = await tenant_suggestion(suggestion_id, db, tenant)
    if item.decision != "accepted":
        raise HTTPException(status.HTTP_409_CONFLICT, "Accept the suggestion before applying it")
    task = await tenant_task(item.task_id, db, tenant)
    patch = (item.revised_content or item.content).get("proposed_patch", {})
    append = patch.get("description_append")
    if not append:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Suggestion has no applicable change")
    task.description += str(append)
    task.version += 1
    item.decision = "applied"
    item.version += 1
    add_audit(
        db, request, tenant.organization_id, user, "suggestion.apply", "task", task.id, {"suggestion_id": item.id}
    )
    await db.commit()
    await db.refresh(task)
    return task


@router.post("/suggestions/{suggestion_id}/feedback", status_code=201)
async def add_feedback(
    suggestion_id: str,
    payload: FeedbackCreate,
    db: DbSession,
    user: CurrentUser,
    tenant: Tenant,
    _: Csrf,
) -> dict[str, str]:
    await AuthorizationService(db).require_permission(
        user, tenant.organization_id, OrganizationPermission.PROJECTS_AI_SUGGEST
    )
    await tenant_suggestion(suggestion_id, db, tenant)
    feedback = AISuggestionFeedback(
        organization_id=tenant.organization_id,
        suggestion_id=suggestion_id,
        user_id=user.id,
        **payload.model_dump(),
    )
    db.add(feedback)
    await db.commit()
    return {"id": feedback.id}


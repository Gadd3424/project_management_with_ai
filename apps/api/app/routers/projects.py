from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response, status
from sqlalchemy import func, select, update

from ..audit import add_audit
from ..dependencies import Csrf, CurrentUser, DbSession, Tenant
from ..domain.permissions import OrganizationPermission
from ..idempotency import find_replayed_resource, store_idempotency
from ..models import OrganizationMember, Project, ProjectAISuggestion, Task, User
from ..project_ai_service import suggest_changes, suggest_defaults, suggest_initial_tasks
from ..rate_limit import limit_suggestion_generation
from ..schemas import (
    ProjectAIFeedback,
    ProjectAISuggestionRead,
    ProjectCreate,
    ProjectDefaultsRequest,
    ProjectDeleteRequest,
    ProjectRead,
    ProjectTaskSuggestionsRequest,
    ProjectUpdate,
    TaskCreate,
    TaskRead,
    TaskReorderRequest,
)
from ..services.authorization_service import AuthorizationService

router = APIRouter(tags=["projects"])


@router.get("/projects", response_model=list[ProjectRead])
async def list_projects(db: DbSession, tenant: Tenant) -> list[Project]:
    return list(
        (
            await db.scalars(
                select(Project)
                .where(
                    Project.organization_id == tenant.organization_id,
                    Project.deleted_at.is_(None),
                )
                .order_by(Project.created_at.desc())
            )
        ).all()
    )


@router.post("/projects", response_model=ProjectRead, status_code=201)
async def create_project(
    payload: ProjectCreate,
    request: Request,
    db: DbSession,
    user: CurrentUser,
    tenant: Tenant,
    _: Csrf,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> Project:
    await AuthorizationService(db).require_permission(
        user, tenant.organization_id, OrganizationPermission.PROJECTS_CREATE
    )
    payload_data = payload.model_dump(mode="json")
    replay = await find_replayed_resource(
        db, tenant.organization_id, idempotency_key, "POST", request.url.path, payload_data
    )
    if replay:
        existing = await db.get(Project, replay.resource_id)
        if existing and existing.organization_id == tenant.organization_id:
            return existing
    project_data = payload.model_dump(
        exclude={"ai_suggestion_id", "ai_task_suggestion_id", "initial_tasks"}
    )
    project = Project(
        organization_id=tenant.organization_id,
        created_by=user.id,
        **project_data,
    )
    db.add(project)
    await db.flush()
    store_idempotency(
        db,
        tenant.organization_id,
        idempotency_key,
        "POST",
        request.url.path,
        payload_data,
        "project",
        project.id,
    )
    add_audit(db, request, tenant.organization_id, user, "project.create", "project", project.id)
    for position, task_payload in enumerate(payload.initial_tasks):
        if task_payload.assignee_id:
            member = await db.scalar(
                select(OrganizationMember).join(User, User.id == OrganizationMember.user_id).where(
                    OrganizationMember.organization_id == tenant.organization_id,
                    OrganizationMember.user_id == task_payload.assignee_id,
                    OrganizationMember.status == "active",
                    OrganizationMember.deleted_at.is_(None),
                    User.status == "active",
                    User.is_active.is_(True),
                )
            )
            if not member:
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Invalid task assignee")
        task = Task(
            organization_id=tenant.organization_id,
            project_id=project.id,
            created_by=user.id,
            status="todo",
            position=position,
            **task_payload.model_dump(),
        )
        db.add(task)
        await db.flush()
        add_audit(db, request, tenant.organization_id, user, "task.create", "task", task.id)
    if payload.ai_suggestion_id:
        suggestion = await db.scalar(
            select(ProjectAISuggestion).where(
                ProjectAISuggestion.id == payload.ai_suggestion_id,
                ProjectAISuggestion.organization_id == tenant.organization_id,
            )
        )
        if suggestion:
            suggestion.project_id = project.id
            suggestion.decision = "accepted"
    if payload.ai_task_suggestion_id:
        task_suggestion = await db.scalar(
            select(ProjectAISuggestion).where(
                ProjectAISuggestion.id == payload.ai_task_suggestion_id,
                ProjectAISuggestion.organization_id == tenant.organization_id,
                ProjectAISuggestion.suggestion_type == "project_initial_tasks",
            )
        )
        if task_suggestion:
            proposed_titles = {
                item.get("title") for item in task_suggestion.proposed_values.get("tasks", [])
            }
            selected_titles = {item.title for item in payload.initial_tasks}
            task_suggestion.project_id = project.id
            task_suggestion.decision = (
                "accepted" if proposed_titles and proposed_titles <= selected_titles else "modified"
            )
    await db.commit()
    await db.refresh(project)
    return project


@router.get("/projects/{project_id}", response_model=ProjectRead)
async def get_project(project_id: str, db: DbSession, tenant: Tenant) -> Project:
    project = await db.scalar(
        select(Project).where(
            Project.id == project_id,
            Project.organization_id == tenant.organization_id,
            Project.deleted_at.is_(None),
        )
    )
    if not project:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Project not found")
    return project


@router.patch("/projects/{project_id}", response_model=ProjectRead)
async def update_project(
    project_id: str,
    payload: ProjectUpdate,
    request: Request,
    db: DbSession,
    user: CurrentUser,
    tenant: Tenant,
    _: Csrf,
) -> Project:
    await AuthorizationService(db).require_permission(
        user, tenant.organization_id, OrganizationPermission.PROJECTS_UPDATE
    )
    changes = payload.model_dump(exclude_unset=True, exclude={"version", "ai_suggestion_id"})
    result = await db.execute(
        update(Project)
        .where(
            Project.id == project_id,
            Project.organization_id == tenant.organization_id,
            Project.version == payload.version,
            Project.deleted_at.is_(None),
        )
        .values(**changes, version=Project.version + 1)
    )
    if result.rowcount == 0:
        raise HTTPException(status.HTTP_409_CONFLICT, "Project changed or no longer exists")
    add_audit(db, request, tenant.organization_id, user, "project.update", "project", project_id, changes)
    if payload.ai_suggestion_id:
        suggestion = await db.scalar(
            select(ProjectAISuggestion).where(
                ProjectAISuggestion.id == payload.ai_suggestion_id,
                ProjectAISuggestion.project_id == project_id,
                ProjectAISuggestion.organization_id == tenant.organization_id,
            )
        )
        if suggestion:
            suggestion.decision = "accepted"
    await db.commit()
    return await get_project(project_id, db, tenant)


@router.delete("/projects/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project(
    project_id: str,
    payload: ProjectDeleteRequest,
    request: Request,
    db: DbSession,
    user: CurrentUser,
    tenant: Tenant,
    _: Csrf,
) -> Response:
    await AuthorizationService(db).require_permission(
        user, tenant.organization_id, OrganizationPermission.PROJECTS_DELETE
    )
    result = await db.execute(
        update(Project)
        .where(
            Project.id == project_id,
            Project.organization_id == tenant.organization_id,
            Project.version == payload.version,
            Project.deleted_at.is_(None),
        )
        .values(deleted_at=datetime.now(UTC), version=Project.version + 1)
    )
    if result.rowcount == 0:
        raise HTTPException(status.HTTP_409_CONFLICT, "Project changed or no longer exists")
    add_audit(db, request, tenant.organization_id, user, "project.delete", "project", project_id)
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _build_project_suggestion(
    *, tenant, user, suggestion_type: str, project_id: str | None, snapshot: dict, result: dict
) -> ProjectAISuggestion:
    return ProjectAISuggestion(
        organization_id=tenant.organization_id,
        project_id=project_id,
        suggestion_type=suggestion_type,
        input_snapshot=snapshot,
        proposed_values=result["proposed_values"],
        confidence=result["confidence"],
        rationale=result["rationale"],
        evidence=result.get("evidence", []),
        assumptions=result.get("assumptions", []),
        risks=result.get("risks", []),
        expected_effect=result.get("expected_effect", ""),
        provider=result["provider"],
        model_id=result.get("model_id"),
        model_version=result.get("model_version"),
        inference_ms=result.get("inference_ms", 0),
        created_by=user.id,
    )


@router.post("/projects/ai/defaults", response_model=ProjectAISuggestionRead, status_code=201)
async def create_project_defaults(
    payload: ProjectDefaultsRequest,
    request: Request,
    db: DbSession,
    user: CurrentUser,
    tenant: Tenant,
    _: Csrf,
    _rate_limit: None = Depends(limit_suggestion_generation),
) -> ProjectAISuggestion:
    await AuthorizationService(db).require_permission(
        user, tenant.organization_id, OrganizationPermission.PROJECTS_AI_SUGGEST
    )
    result = await suggest_defaults(db, tenant.organization_id, payload.name)
    suggestion = _build_project_suggestion(
        tenant=tenant,
        user=user,
        suggestion_type="project_defaults",
        project_id=None,
        snapshot={"name": payload.name},
        result=result,
    )
    db.add(suggestion)
    await db.flush()
    add_audit(
        db,
        request,
        tenant.organization_id,
        user,
        "project.ai_defaults.generate",
        "project_ai_suggestion",
        suggestion.id,
    )
    await db.commit()
    await db.refresh(suggestion)
    return suggestion


@router.post(
    "/projects/{project_id}/ai/change-proposal",
    response_model=ProjectAISuggestionRead,
    status_code=201,
)
async def create_project_change_proposal(
    project_id: str,
    request: Request,
    db: DbSession,
    user: CurrentUser,
    tenant: Tenant,
    _: Csrf,
    _rate_limit: None = Depends(limit_suggestion_generation),
) -> ProjectAISuggestion:
    await AuthorizationService(db).require_permission(
        user, tenant.organization_id, OrganizationPermission.PROJECTS_AI_SUGGEST
    )
    project = await get_project(project_id, db, tenant)
    snapshot, result = await suggest_changes(db, project)
    suggestion = _build_project_suggestion(
        tenant=tenant,
        user=user,
        suggestion_type="project_change_proposal",
        project_id=project.id,
        snapshot=snapshot,
        result=result,
    )
    db.add(suggestion)
    await db.flush()
    add_audit(
        db,
        request,
        tenant.organization_id,
        user,
        "project.ai_change_proposal.generate",
        "project_ai_suggestion",
        suggestion.id,
    )
    await db.commit()
    await db.refresh(suggestion)
    return suggestion


@router.post(
    "/projects/ai/task-suggestions",
    response_model=ProjectAISuggestionRead,
    status_code=201,
)
async def create_project_task_suggestions(
    payload: ProjectTaskSuggestionsRequest,
    request: Request,
    db: DbSession,
    user: CurrentUser,
    tenant: Tenant,
    _: Csrf,
    _rate_limit: None = Depends(limit_suggestion_generation),
) -> ProjectAISuggestion:
    await AuthorizationService(db).require_permission(
        user, tenant.organization_id, OrganizationPermission.PROJECTS_AI_SUGGEST
    )
    snapshot = payload.model_dump(mode="json")
    result = await suggest_initial_tasks(db, tenant.organization_id, snapshot)
    suggestion = _build_project_suggestion(
        tenant=tenant,
        user=user,
        suggestion_type="project_initial_tasks",
        project_id=None,
        snapshot=snapshot,
        result=result,
    )
    db.add(suggestion)
    await db.flush()
    add_audit(
        db,
        request,
        tenant.organization_id,
        user,
        "project.ai_initial_tasks.generate",
        "project_ai_suggestion",
        suggestion.id,
    )
    await db.commit()
    await db.refresh(suggestion)
    return suggestion


@router.post("/project-ai-suggestions/{suggestion_id}/feedback", response_model=ProjectAISuggestionRead)
async def project_ai_feedback(
    suggestion_id: str,
    payload: ProjectAIFeedback,
    request: Request,
    db: DbSession,
    user: CurrentUser,
    tenant: Tenant,
    _: Csrf,
) -> ProjectAISuggestion:
    await AuthorizationService(db).require_permission(
        user, tenant.organization_id, OrganizationPermission.PROJECTS_AI_SUGGEST
    )
    suggestion = await db.scalar(
        select(ProjectAISuggestion).where(
            ProjectAISuggestion.id == suggestion_id,
            ProjectAISuggestion.organization_id == tenant.organization_id,
            ProjectAISuggestion.deleted_at.is_(None),
        )
    )
    if not suggestion:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Project AI suggestion not found")
    suggestion.decision = payload.decision
    suggestion.feedback_rating = payload.rating
    suggestion.feedback_comment = payload.comment
    add_audit(db, request, tenant.organization_id, user, "project.ai_feedback", "project_ai_suggestion", suggestion.id)
    await db.commit()
    await db.refresh(suggestion)
    return suggestion


@router.get("/projects/{project_id}/tasks", response_model=list[TaskRead])
async def list_tasks(project_id: str, db: DbSession, tenant: Tenant) -> list[Task]:
    project = await get_project(project_id, db, tenant)
    return list(
        (
            await db.scalars(
                select(Task)
                .where(
                    Task.project_id == project.id,
                    Task.organization_id == tenant.organization_id,
                    Task.deleted_at.is_(None),
                )
                .order_by(Task.status, Task.position, Task.created_at)
            )
        ).all()
    )


@router.post("/projects/{project_id}/tasks", response_model=TaskRead, status_code=201)
async def create_task(
    project_id: str,
    payload: TaskCreate,
    request: Request,
    db: DbSession,
    user: CurrentUser,
    tenant: Tenant,
    _: Csrf,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> Task:
    await AuthorizationService(db).require_permission(
        user, tenant.organization_id, OrganizationPermission.PROJECTS_UPDATE
    )
    project = await get_project(project_id, db, tenant)
    if payload.assignee_id:
        member = await db.scalar(
            select(OrganizationMember).join(User, User.id == OrganizationMember.user_id).where(
                OrganizationMember.organization_id == tenant.organization_id,
                OrganizationMember.user_id == payload.assignee_id,
                OrganizationMember.status == "active",
                OrganizationMember.deleted_at.is_(None),
                User.status == "active",
                User.is_active.is_(True),
            )
        )
        if not member:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Invalid task assignee")
    if payload.parent_id:
        parent = await db.scalar(
            select(Task).where(
                Task.id == payload.parent_id,
                Task.project_id == project.id,
                Task.organization_id == tenant.organization_id,
                Task.deleted_at.is_(None),
            )
        )
        if not parent:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Invalid parent task")
    next_position = (await db.scalar(
        select(func.coalesce(func.max(Task.position), -1)).where(
            Task.project_id == project.id,
            Task.status == "todo",
            Task.deleted_at.is_(None),
        )
    )) + 1
    payload_data = payload.model_dump(mode="json")
    replay = await find_replayed_resource(
        db, tenant.organization_id, idempotency_key, "POST", request.url.path, payload_data
    )
    if replay:
        existing = await db.get(Task, replay.resource_id)
        if existing and existing.organization_id == tenant.organization_id:
            return existing
    task = Task(
        organization_id=tenant.organization_id,
        project_id=project.id,
        created_by=user.id,
        status="todo",
        position=next_position,
        **payload.model_dump(),
    )
    db.add(task)
    await db.flush()
    store_idempotency(
        db,
        tenant.organization_id,
        idempotency_key,
        "POST",
        request.url.path,
        payload_data,
        "task",
        task.id,
    )
    add_audit(db, request, tenant.organization_id, user, "task.create", "task", task.id)
    await db.commit()
    await db.refresh(task)
    return task


@router.patch("/projects/{project_id}/tasks/reorder", response_model=list[TaskRead])
async def reorder_tasks(
    project_id: str,
    payload: TaskReorderRequest,
    request: Request,
    db: DbSession,
    user: CurrentUser,
    tenant: Tenant,
    _: Csrf,
) -> list[Task]:
    await AuthorizationService(db).require_permission(
        user, tenant.organization_id, OrganizationPermission.PROJECTS_UPDATE
    )
    await get_project(project_id, db, tenant)
    if len({item.id for item in payload.tasks}) != len(payload.tasks):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Duplicate task id")
    for item in payload.tasks:
        result = await db.execute(
            update(Task)
            .where(
                Task.id == item.id,
                Task.project_id == project_id,
                Task.organization_id == tenant.organization_id,
                Task.version == item.version,
                Task.deleted_at.is_(None),
            )
            .values(status=item.status, position=item.position, version=Task.version + 1)
        )
        if result.rowcount != 1:
            await db.rollback()
            raise HTTPException(status.HTTP_409_CONFLICT, "Task order changed or task no longer exists")
    add_audit(
        db,
        request,
        tenant.organization_id,
        user,
        "task.reorder",
        "project",
        project_id,
        {"tasks": [item.model_dump() for item in payload.tasks]},
    )
    await db.commit()
    return await list_tasks(project_id, db, tenant)

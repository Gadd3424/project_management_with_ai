from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Request, Response, status
from sqlalchemy import select, update

from ..audit import add_audit
from ..dependencies import Csrf, CurrentUser, DbSession, Tenant
from ..domain.permissions import OrganizationPermission
from ..models import Comment, OrganizationMember, Project, Task, User
from ..project_access import accessible_project
from ..schemas import CommentCreate, CommentRead, TaskAssigneeRead, TaskDeleteRequest, TaskRead, TaskUpdate
from ..services.authorization_service import AuthorizationService

router = APIRouter(tags=["tasks"])


@router.get("/task-assignees", response_model=list[TaskAssigneeRead])
async def list_task_assignees(db: DbSession, user: CurrentUser, tenant: Tenant) -> list[TaskAssigneeRead]:
    await AuthorizationService(db).require_permission(
        user, tenant.organization_id, OrganizationPermission.PROJECTS_UPDATE
    )
    rows = (
        await db.execute(
            select(User.id, User.display_name)
            .join(OrganizationMember, OrganizationMember.user_id == User.id)
            .where(
                OrganizationMember.organization_id == tenant.organization_id,
                OrganizationMember.status == "active",
                OrganizationMember.deleted_at.is_(None),
                User.deleted_at.is_(None),
                User.status == "active",
                User.is_active.is_(True),
            )
            .order_by(User.display_name)
        )
    ).all()
    return [TaskAssigneeRead(id=row.id, display_name=row.display_name) for row in rows]


async def tenant_task(task_id: str, db: DbSession, tenant: Tenant) -> Task:
    task = await db.scalar(
        select(Task)
        .join(Project, Task.project_id == Project.id)
        .where(
            Task.id == task_id,
            Task.organization_id == tenant.organization_id,
            Task.deleted_at.is_(None),
            Project.organization_id == tenant.organization_id,
            Project.deleted_at.is_(None),
        )
    )
    if not task:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Task not found")
    await accessible_project(db, task.project_id, tenant)
    return task


@router.get("/tasks/{task_id}", response_model=TaskRead)
async def get_task(task_id: str, db: DbSession, tenant: Tenant) -> Task:
    return await tenant_task(task_id, db, tenant)


@router.patch("/tasks/{task_id}", response_model=TaskRead)
async def update_task(
    task_id: str,
    payload: TaskUpdate,
    request: Request,
    db: DbSession,
    user: CurrentUser,
    tenant: Tenant,
    _: Csrf,
) -> Task:
    await AuthorizationService(db).require_permission(
        user, tenant.organization_id, OrganizationPermission.PROJECTS_UPDATE
    )
    task = await tenant_task(task_id, db, tenant)
    await accessible_project(db, task.project_id, tenant, edit=True)
    changes = payload.model_dump(exclude_unset=True, exclude={"version"})
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
    result = await db.execute(
        update(Task)
        .where(
            Task.id == task_id,
            Task.organization_id == tenant.organization_id,
            Task.version == payload.version,
            Task.deleted_at.is_(None),
        )
        .values(**changes, version=Task.version + 1)
    )
    if result.rowcount == 0:
        raise HTTPException(status.HTTP_409_CONFLICT, "Task changed or no longer exists")
    add_audit(db, request, tenant.organization_id, user, "task.update", "task", task_id, changes)
    await db.commit()
    return await tenant_task(task_id, db, tenant)


@router.delete("/tasks/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_task(
    task_id: str,
    payload: TaskDeleteRequest,
    request: Request,
    db: DbSession,
    user: CurrentUser,
    tenant: Tenant,
    _: Csrf,
) -> Response:
    await AuthorizationService(db).require_permission(
        user, tenant.organization_id, OrganizationPermission.PROJECTS_UPDATE
    )
    task = await tenant_task(task_id, db, tenant)
    await accessible_project(db, task.project_id, tenant, edit=True)
    if task.version != payload.version:
        raise HTTPException(status.HTTP_409_CONFLICT, "Task changed or no longer exists")
    task.deleted_at = datetime.now(UTC)
    task.version += 1
    add_audit(db, request, tenant.organization_id, user, "task.delete", "task", task_id)
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/tasks/{task_id}/comments", response_model=list[CommentRead])
async def list_comments(task_id: str, db: DbSession, tenant: Tenant) -> list[Comment]:
    await tenant_task(task_id, db, tenant)
    return list(
        (
            await db.scalars(
                select(Comment)
                .where(
                    Comment.task_id == task_id,
                    Comment.organization_id == tenant.organization_id,
                    Comment.deleted_at.is_(None),
                )
                .order_by(Comment.created_at)
            )
        ).all()
    )


@router.post("/tasks/{task_id}/comments", response_model=CommentRead, status_code=201)
async def create_comment(
    task_id: str,
    payload: CommentCreate,
    request: Request,
    db: DbSession,
    user: CurrentUser,
    tenant: Tenant,
    _: Csrf,
) -> Comment:
    await AuthorizationService(db).require_permission(
        user, tenant.organization_id, OrganizationPermission.PROJECTS_UPDATE
    )
    task = await tenant_task(task_id, db, tenant)
    await accessible_project(db, task.project_id, tenant, edit=True)
    comment = Comment(
        organization_id=tenant.organization_id,
        task_id=task_id,
        body=payload.body,
        created_by=user.id,
    )
    db.add(comment)
    await db.flush()
    add_audit(db, request, tenant.organization_id, user, "comment.create", "comment", comment.id)
    await db.commit()
    await db.refresh(comment)
    return comment

from fastapi import APIRouter, HTTPException, Request, status
from sqlalchemy import select, update

from ..audit import add_audit
from ..dependencies import Csrf, CurrentUser, DbSession, Tenant
from ..models import Comment, Task
from ..schemas import CommentCreate, CommentRead, TaskRead, TaskUpdate

router = APIRouter(tags=["tasks"])


async def tenant_task(task_id: str, db: DbSession, tenant: Tenant) -> Task:
    task = await db.scalar(
        select(Task).where(
            Task.id == task_id,
            Task.organization_id == tenant.organization_id,
            Task.deleted_at.is_(None),
        )
    )
    if not task:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Task not found")
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
    changes = payload.model_dump(exclude_unset=True, exclude={"version"})
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
    await tenant_task(task_id, db, tenant)
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

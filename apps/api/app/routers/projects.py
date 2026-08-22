from typing import Annotated

from fastapi import APIRouter, Header, HTTPException, Request, status
from sqlalchemy import select, update

from ..audit import add_audit
from ..dependencies import Csrf, CurrentUser, DbSession, Tenant
from ..idempotency import find_replayed_resource, store_idempotency
from ..models import Project, Task
from ..schemas import ProjectCreate, ProjectRead, ProjectUpdate, TaskCreate, TaskRead

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
    payload_data = payload.model_dump(mode="json")
    replay = await find_replayed_resource(
        db, tenant.organization_id, idempotency_key, "POST", request.url.path, payload_data
    )
    if replay:
        existing = await db.get(Project, replay.resource_id)
        if existing and existing.organization_id == tenant.organization_id:
            return existing
    project = Project(
        organization_id=tenant.organization_id,
        name=payload.name,
        description=payload.description,
        created_by=user.id,
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
    changes = payload.model_dump(exclude_unset=True, exclude={"version"})
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
    await db.commit()
    return await get_project(project_id, db, tenant)


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
    project = await get_project(project_id, db, tenant)
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

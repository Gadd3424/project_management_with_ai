from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Query, Request, Response, status
from sqlalchemy import func, select

from ..audit import add_audit
from ..dependencies import Csrf, CurrentUser, DbSession, Tenant
from ..models import OrganizationMember, Project, ProjectMember, ProjectMessage, Task, User
from ..project_access import MANAGER_ROLES, accessible_project
from ..schemas import (
    ProjectInvitationCreate,
    ProjectInvitationDecision,
    ProjectInviteCandidate,
    ProjectMemberRead,
    ProjectMemberUpdate,
    ProjectMessageCreate,
    ProjectMessagePage,
    ProjectMessageRead,
    ProjectSummary,
)

router = APIRouter(tags=["project collaboration"])


def _role(value) -> str:
    return value.value if hasattr(value, "value") else str(value)


def _member_read(member: ProjectMember, user: User, organization_role) -> ProjectMemberRead:
    return ProjectMemberRead(
        id=member.id,
        user_id=user.id,
        display_name=user.display_name if not user.deleted_at else "削除済みユーザー",
        email=user.email,
        organization_role=_role(organization_role),
        role=member.role,
        invitation_status=member.invitation_status,
        invited_at=member.invited_at,
        joined_at=member.joined_at,
        version=member.version,
    )


async def _membership(db: DbSession, project_id: str, user_id: str, organization_id: str) -> ProjectMember | None:
    return await db.scalar(
        select(ProjectMember).where(
            ProjectMember.project_id == project_id,
            ProjectMember.user_id == user_id,
            ProjectMember.organization_id == organization_id,
            ProjectMember.deleted_at.is_(None),
        )
    )


async def _ensure_manager(tenant: Tenant) -> None:
    if tenant.role not in MANAGER_ROLES:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Owner or admin role required")


async def _ensure_not_last_project_admin(db: DbSession, member: ProjectMember) -> None:
    if member.role != "project_admin" or member.invitation_status != "accepted":
        return
    admin_count = await db.scalar(
        select(func.count(ProjectMember.id)).where(
            ProjectMember.project_id == member.project_id,
            ProjectMember.role == "project_admin",
            ProjectMember.invitation_status == "accepted",
            ProjectMember.deleted_at.is_(None),
        )
    )
    if (admin_count or 0) <= 1:
        raise HTTPException(status.HTTP_409_CONFLICT, "The last project administrator cannot be changed")


@router.get("/project-dashboard", response_model=list[ProjectSummary])
async def project_dashboard(db: DbSession, user: CurrentUser, tenant: Tenant) -> list[ProjectSummary]:
    query = select(Project).where(
        Project.organization_id == tenant.organization_id,
        Project.deleted_at.is_(None),
    )
    if tenant.role not in MANAGER_ROLES:
        query = query.join(ProjectMember, ProjectMember.project_id == Project.id).where(
            ProjectMember.user_id == user.id,
            ProjectMember.invitation_status == "accepted",
            ProjectMember.deleted_at.is_(None),
        )
    projects = list((await db.scalars(query.order_by(Project.updated_at.desc()))).all())
    result: list[ProjectSummary] = []
    for project in projects:
        member = await _membership(db, project.id, user.id, tenant.organization_id)
        rows = (
            await db.execute(
                select(Task.status, func.count(Task.id))
                .where(Task.project_id == project.id, Task.deleted_at.is_(None))
                .group_by(Task.status)
            )
        ).all()
        counts = {name: 0 for name in ("todo", "in_progress", "on_hold", "done")}
        counts.update({str(row[0]): int(row[1]) for row in rows})
        task_count = sum(counts.values())
        last_read = member.last_read_at if member and member.last_read_at else datetime(1970, 1, 1, tzinfo=UTC)
        unread = await db.scalar(
            select(func.count(ProjectMessage.id)).where(
                ProjectMessage.project_id == project.id,
                ProjectMessage.organization_id == tenant.organization_id,
                ProjectMessage.author_id != user.id,
                ProjectMessage.created_at > last_read,
                ProjectMessage.deleted_at.is_(None),
            )
        )
        result.append(
            ProjectSummary(
                **project.__dict__,
                my_role="project_admin" if tenant.role in MANAGER_ROLES else member.role,
                task_count=task_count,
                status_counts=counts,
                completion_rate=round(counts["done"] / task_count, 3) if task_count else 0.0,
                unread_count=int(unread or 0),
            )
        )
    return result


@router.get("/project-invitations", response_model=list[ProjectMemberRead])
async def my_project_invitations(db: DbSession, user: CurrentUser, tenant: Tenant) -> list[ProjectMemberRead]:
    rows = (
        await db.execute(
            select(ProjectMember, User, OrganizationMember.role, Project.name)
            .join(User, User.id == ProjectMember.user_id)
            .join(Project, Project.id == ProjectMember.project_id)
            .join(
                OrganizationMember,
                (OrganizationMember.user_id == User.id)
                & (OrganizationMember.organization_id == ProjectMember.organization_id),
            )
            .where(
                ProjectMember.organization_id == tenant.organization_id,
                ProjectMember.user_id == user.id,
                ProjectMember.invitation_status == "pending",
                ProjectMember.deleted_at.is_(None),
            )
        )
    ).all()
    return [_member_read(row[0], row[1], row[2]).model_copy(update={"project_name": row[3]}) for row in rows]


@router.get("/projects/{project_id}/members", response_model=list[ProjectMemberRead])
async def list_project_members(project_id: str, db: DbSession, tenant: Tenant) -> list[ProjectMemberRead]:
    await accessible_project(db, project_id, tenant)
    rows = (
        await db.execute(
            select(ProjectMember, User, OrganizationMember.role)
            .join(User, User.id == ProjectMember.user_id)
            .join(
                OrganizationMember,
                (OrganizationMember.user_id == User.id)
                & (OrganizationMember.organization_id == ProjectMember.organization_id),
            )
            .where(
                ProjectMember.project_id == project_id,
                ProjectMember.organization_id == tenant.organization_id,
                ProjectMember.deleted_at.is_(None),
                ProjectMember.invitation_status.in_(["accepted", "pending"]),
            )
            .order_by(ProjectMember.invitation_status, User.display_name)
        )
    ).all()
    return [_member_read(*row) for row in rows]


@router.get("/projects/{project_id}/invite-candidates", response_model=list[ProjectInviteCandidate])
async def invite_candidates(project_id: str, db: DbSession, tenant: Tenant) -> list[ProjectInviteCandidate]:
    await _ensure_manager(tenant)
    await accessible_project(db, project_id, tenant, manage=True)
    rows = (
        await db.execute(
            select(OrganizationMember, User, ProjectMember)
            .join(User, User.id == OrganizationMember.user_id)
            .outerjoin(
                ProjectMember,
                (ProjectMember.project_id == project_id)
                & (ProjectMember.user_id == User.id)
                & (ProjectMember.deleted_at.is_(None)),
            )
            .where(
                OrganizationMember.organization_id == tenant.organization_id,
                OrganizationMember.role.in_(["member", "viewer"]),
                OrganizationMember.status == "active",
                OrganizationMember.deleted_at.is_(None),
                User.status == "active",
                User.is_active.is_(True),
                User.deleted_at.is_(None),
            )
            .order_by(User.display_name)
        )
    ).all()
    return [
        ProjectInviteCandidate(
            user_id=target.id,
            display_name=target.display_name,
            email=target.email,
            organization_role=_role(org_member.role),
            membership_status=project_member.invitation_status if project_member else None,
        )
        for org_member, target, project_member in rows
    ]


@router.post("/projects/{project_id}/invitations", response_model=list[ProjectMemberRead], status_code=201)
async def invite_project_members(
    project_id: str,
    payload: ProjectInvitationCreate,
    request: Request,
    db: DbSession,
    user: CurrentUser,
    tenant: Tenant,
    _: Csrf,
) -> list[ProjectMemberRead]:
    await _ensure_manager(tenant)
    await accessible_project(db, project_id, tenant, manage=True)
    if len({item.user_id for item in payload.invitations}) != len(payload.invitations):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Duplicate invitation target")
    created: list[ProjectMember] = []
    for invitation in payload.invitations:
        row = await db.execute(
            select(OrganizationMember, User)
            .join(User, User.id == OrganizationMember.user_id)
            .where(
                OrganizationMember.organization_id == tenant.organization_id,
                OrganizationMember.user_id == invitation.user_id,
                OrganizationMember.role.in_(["member", "viewer"]),
                OrganizationMember.status == "active",
                OrganizationMember.deleted_at.is_(None),
                User.status == "active",
                User.is_active.is_(True),
                User.deleted_at.is_(None),
            )
        )
        target = row.first()
        if not target:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Invalid invitation target")
        org_member, target_user = target
        allowed_role = "viewer" if _role(org_member.role) == "viewer" else invitation.role
        if _role(org_member.role) == "viewer" and invitation.role != "viewer":
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Viewer cannot become editor")
        existing = await db.scalar(
            select(ProjectMember).where(
                ProjectMember.project_id == project_id,
                ProjectMember.user_id == target_user.id,
            )
        )
        if existing and not existing.deleted_at and existing.invitation_status in {"accepted", "pending"}:
            raise HTTPException(status.HTTP_409_CONFLICT, "User is already invited or participating")
        now = datetime.now(UTC)
        if existing:
            existing.deleted_at = None
            existing.role = allowed_role
            existing.invitation_status = "pending"
            existing.invited_by = user.id
            existing.invited_at = now
            existing.joined_at = None
            existing.version += 1
            member = existing
        else:
            member = ProjectMember(
                organization_id=tenant.organization_id,
                project_id=project_id,
                user_id=target_user.id,
                role=allowed_role,
                invitation_status="pending",
                invited_by=user.id,
                invited_at=now,
            )
            db.add(member)
        await db.flush()
        created.append(member)
        add_audit(db, request, tenant.organization_id, user, "project.member.invite", "project_member", member.id)
    await db.commit()
    members = await list_project_members(project_id, db, tenant)
    ids = {member.id for member in created}
    return [member for member in members if member.id in ids]


async def _decide_invitation(
    invitation_id: str,
    payload: ProjectInvitationDecision,
    decision: str,
    request: Request,
    db: DbSession,
    user: CurrentUser,
    tenant: Tenant,
) -> ProjectMember:
    member = await db.scalar(
        select(ProjectMember).where(
            ProjectMember.id == invitation_id,
            ProjectMember.user_id == user.id,
            ProjectMember.organization_id == tenant.organization_id,
            ProjectMember.invitation_status == "pending",
            ProjectMember.version == payload.version,
            ProjectMember.deleted_at.is_(None),
        )
    )
    if not member:
        raise HTTPException(status.HTTP_409_CONFLICT, "Invitation changed or no longer exists")
    member.invitation_status = decision
    member.joined_at = datetime.now(UTC) if decision == "accepted" else None
    member.version += 1
    add_audit(db, request, tenant.organization_id, user, f"project.invitation.{decision}", "project_member", member.id)
    await db.commit()
    await db.refresh(member)
    return member


@router.post("/project-invitations/{invitation_id}/accept", status_code=204)
async def accept_invitation(
    invitation_id: str,
    payload: ProjectInvitationDecision,
    request: Request,
    db: DbSession,
    user: CurrentUser,
    tenant: Tenant,
    _: Csrf,
) -> Response:
    await _decide_invitation(invitation_id, payload, "accepted", request, db, user, tenant)
    return Response(status_code=204)


@router.post("/project-invitations/{invitation_id}/decline", status_code=204)
async def decline_invitation(
    invitation_id: str,
    payload: ProjectInvitationDecision,
    request: Request,
    db: DbSession,
    user: CurrentUser,
    tenant: Tenant,
    _: Csrf,
) -> Response:
    await _decide_invitation(invitation_id, payload, "declined", request, db, user, tenant)
    return Response(status_code=204)


@router.patch("/projects/{project_id}/members/{member_id}", status_code=204)
async def update_project_member(
    project_id: str,
    member_id: str,
    payload: ProjectMemberUpdate,
    request: Request,
    db: DbSession,
    user: CurrentUser,
    tenant: Tenant,
    _: Csrf,
) -> Response:
    await _ensure_manager(tenant)
    await accessible_project(db, project_id, tenant, manage=True)
    member = await db.scalar(
        select(ProjectMember).where(
            ProjectMember.id == member_id,
            ProjectMember.project_id == project_id,
            ProjectMember.version == payload.version,
            ProjectMember.deleted_at.is_(None),
        )
    )
    if not member:
        raise HTTPException(status.HTTP_409_CONFLICT, "Project member changed or no longer exists")
    if member.role == "project_admin" and payload.role != "project_admin":
        await _ensure_not_last_project_admin(db, member)
    org_role = await db.scalar(
        select(OrganizationMember.role).where(
            OrganizationMember.organization_id == tenant.organization_id,
            OrganizationMember.user_id == member.user_id,
            OrganizationMember.status == "active",
        )
    )
    if _role(org_role) == "viewer" and payload.role != "viewer":
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Viewer cannot become editor")
    member.role = payload.role
    member.version += 1
    add_audit(db, request, tenant.organization_id, user, "project.member.role_change", "project_member", member.id)
    await db.commit()
    return Response(status_code=204)


@router.delete("/projects/{project_id}/members/{member_id}", status_code=204)
async def remove_project_member(
    project_id: str,
    member_id: str,
    payload: ProjectInvitationDecision,
    request: Request,
    db: DbSession,
    user: CurrentUser,
    tenant: Tenant,
    _: Csrf,
) -> Response:
    await _ensure_manager(tenant)
    await accessible_project(db, project_id, tenant, manage=True)
    member = await db.scalar(
        select(ProjectMember).where(
            ProjectMember.id == member_id,
            ProjectMember.project_id == project_id,
            ProjectMember.version == payload.version,
            ProjectMember.deleted_at.is_(None),
        )
    )
    if not member:
        raise HTTPException(status.HTTP_409_CONFLICT, "Project member changed or no longer exists")
    await _ensure_not_last_project_admin(db, member)
    member.invitation_status = "revoked"
    member.deleted_at = datetime.now(UTC)
    member.version += 1
    add_audit(db, request, tenant.organization_id, user, "project.member.remove", "project_member", member.id)
    await db.commit()
    return Response(status_code=204)


@router.get("/projects/{project_id}/messages", response_model=ProjectMessagePage)
async def list_project_messages(
    project_id: str, db: DbSession, tenant: Tenant, before: datetime | None = None, limit: int = Query(50, ge=1, le=100)
) -> ProjectMessagePage:
    await accessible_project(db, project_id, tenant)
    filters = [
        ProjectMessage.project_id == project_id,
        ProjectMessage.organization_id == tenant.organization_id,
        ProjectMessage.deleted_at.is_(None),
    ]
    if before:
        filters.append(ProjectMessage.created_at < before)
    rows = (
        await db.execute(
            select(ProjectMessage, User)
            .join(User, User.id == ProjectMessage.author_id)
            .where(*filters)
            .order_by(ProjectMessage.created_at.desc())
            .limit(limit + 1)
        )
    ).all()
    has_more = len(rows) > limit
    rows = rows[:limit]
    items = [
        ProjectMessageRead(
            id=message.id,
            project_id=message.project_id,
            author_id=message.author_id,
            author_name=author.display_name if not author.deleted_at else "削除済みユーザー",
            body=message.body,
            created_at=message.created_at,
        )
        for message, author in reversed(rows)
    ]
    return ProjectMessagePage(items=items, next_before=rows[-1][0].created_at if has_more and rows else None)


@router.post("/projects/{project_id}/messages", response_model=ProjectMessageRead, status_code=201)
async def create_project_message(
    project_id: str,
    payload: ProjectMessageCreate,
    request: Request,
    db: DbSession,
    user: CurrentUser,
    tenant: Tenant,
    _: Csrf,
) -> ProjectMessageRead:
    await accessible_project(db, project_id, tenant)
    body = payload.body.strip()
    if not body:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Message cannot be empty")
    message = ProjectMessage(
        organization_id=tenant.organization_id, project_id=project_id, author_id=user.id, body=body
    )
    db.add(message)
    await db.flush()
    add_audit(db, request, tenant.organization_id, user, "project.message.create", "project_message", message.id)
    await db.commit()
    await db.refresh(message)
    return ProjectMessageRead(
        id=message.id,
        project_id=project_id,
        author_id=user.id,
        author_name=user.display_name,
        body=message.body,
        created_at=message.created_at,
    )


@router.post("/projects/{project_id}/messages/read", status_code=204)
async def mark_messages_read(project_id: str, db: DbSession, user: CurrentUser, tenant: Tenant, _: Csrf) -> Response:
    await accessible_project(db, project_id, tenant)
    member = await _membership(db, project_id, user.id, tenant.organization_id)
    if not member and tenant.role in MANAGER_ROLES:
        member = ProjectMember(
            organization_id=tenant.organization_id,
            project_id=project_id,
            user_id=user.id,
            role="project_admin",
            invitation_status="accepted",
            invited_by=user.id,
            joined_at=datetime.now(UTC),
        )
        db.add(member)
    if member:
        member.last_read_at = datetime.now(UTC)
    await db.commit()
    return Response(status_code=204)

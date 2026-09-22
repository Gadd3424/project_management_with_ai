from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .dependencies import TenantContext
from .models import Project, ProjectMember

MANAGER_ROLES = {"owner", "admin"}


async def accessible_project(
    db: AsyncSession, project_id: str, tenant: TenantContext, *, edit: bool = False, manage: bool = False
) -> tuple[Project, ProjectMember | None]:
    project = await db.scalar(
        select(Project).where(
            Project.id == project_id,
            Project.organization_id == tenant.organization_id,
            Project.deleted_at.is_(None),
        )
    )
    if not project:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Project not found")
    if tenant.role in MANAGER_ROLES:
        return project, None
    member = await db.scalar(
        select(ProjectMember).where(
            ProjectMember.project_id == project_id,
            ProjectMember.organization_id == tenant.organization_id,
            ProjectMember.user_id == getattr(tenant, "user_id", ""),
            ProjectMember.invitation_status == "accepted",
            ProjectMember.deleted_at.is_(None),
        )
    )
    if not member:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Project not found")
    if manage or (edit and member.role not in {"project_admin", "editor"}):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Project permission denied")
    return project, member

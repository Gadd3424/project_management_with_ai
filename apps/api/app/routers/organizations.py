from fastapi import APIRouter
from sqlalchemy import select

from ..dependencies import CurrentUser, DbSession
from ..models import Organization, OrganizationMember

router = APIRouter(prefix="/organizations", tags=["organizations"])


@router.get("")
async def list_organizations(db: DbSession, user: CurrentUser) -> list[dict[str, str]]:
    rows = (
        await db.execute(
            select(Organization, OrganizationMember.role)
            .join(OrganizationMember, OrganizationMember.organization_id == Organization.id)
            .where(
                OrganizationMember.user_id == user.id,
                OrganizationMember.deleted_at.is_(None),
                Organization.deleted_at.is_(None),
            )
        )
    ).all()
    return [{"id": org.id, "name": org.name, "slug": org.slug, "role": role} for org, role in rows]

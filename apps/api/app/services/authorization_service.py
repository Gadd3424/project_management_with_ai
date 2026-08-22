from fastapi import status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..domain.permissions import OrganizationPermission, permissions_for_role
from ..domain.roles import MembershipStatus, OrganizationRole
from ..errors import DomainError
from ..models import Organization, OrganizationMember, User


class AuthorizationService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_member(self, user_id: str, organization_id: str) -> OrganizationMember:
        member = await self.db.scalar(
            select(OrganizationMember).where(
                OrganizationMember.organization_id == organization_id,
                OrganizationMember.user_id == user_id,
                OrganizationMember.deleted_at.is_(None),
                OrganizationMember.status == MembershipStatus.ACTIVE,
            )
        )
        if not member:
            raise DomainError(
                "CROSS_ORGANIZATION_ACCESS_DENIED",
                "対象組織へのアクセス権がありません。",
                status.HTTP_403_FORBIDDEN,
            )
        return member

    async def require_permission(
        self, actor: User, organization_id: str, permission: OrganizationPermission
    ) -> OrganizationMember:
        member = await self.get_member(actor.id, organization_id)
        if permission not in permissions_for_role(member.role):
            raise DomainError("FORBIDDEN", "この操作を実行する権限がありません。", status.HTTP_403_FORBIDDEN)
        return member

    async def lock_organization(self, organization_id: str) -> Organization:
        organization = await self.db.scalar(
            select(Organization).where(Organization.id == organization_id).with_for_update()
        )
        if not organization:
            raise DomainError("ORGANIZATION_NOT_FOUND", "組織が見つかりません。", status.HTTP_404_NOT_FOUND)
        return organization


def role_value(role: OrganizationRole | str) -> OrganizationRole:
    return role if isinstance(role, OrganizationRole) else OrganizationRole(role)

from fastapi import Request, status

from ..domain.permissions import OrganizationPermission
from ..domain.roles import OrganizationRole
from ..errors import DomainError
from ..models import User
from ..security import verify_password
from .audit_service import add_management_audit
from .authorization_service import AuthorizationService
from .user_management_service import UserManagementService


class OwnershipService:
    def __init__(self, db):
        self.db = db
        self.authorization = AuthorizationService(db)
        self.users = UserManagementService(db)

    async def transfer(
        self, actor: User, organization_id: str, new_owner_user_id: str, password: str, request: Request
    ) -> None:
        actor_member = await self.authorization.require_permission(
            actor, organization_id, OrganizationPermission.OWNERSHIP_TRANSFER
        )
        if not verify_password(password, actor.password_hash):
            raise DomainError("REAUTHENTICATION_FAILED", "再認証に失敗しました。", status.HTTP_401_UNAUTHORIZED)
        if actor.id == new_owner_user_id:
            raise DomainError("FORBIDDEN", "自分自身へ所有権を移譲できません。", status.HTTP_409_CONFLICT)
        await self.authorization.lock_organization(organization_id)
        target_member, target_user = await self.users.target_member(organization_id, new_owner_user_id, lock=True)
        previous_target_role = target_member.role.value
        actor_member.role = OrganizationRole.ADMIN
        actor_member.version += 1
        target_member.role = OrganizationRole.OWNER
        target_member.version += 1
        actor.auth_version += 1
        target_user.auth_version += 1
        add_management_audit(
            self.db,
            request,
            organization_id,
            actor,
            "organization.ownership.transfer",
            target_user.id,
            previous_values={"old_owner_id": actor.id, "new_owner_role": previous_target_role},
            new_values={"new_owner_id": target_user.id, "old_owner_role": "admin"},
        )
        await self.db.commit()

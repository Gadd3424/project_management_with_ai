from fastapi import status

from ..domain.roles import OrganizationRole
from ..errors import DomainError
from ..models import Organization, OrganizationMember
from ..services.authorization_service import role_value


class OrganizationUserPolicy:
    @staticmethod
    def require_can_manage(
        actor: OrganizationMember,
        target: OrganizationMember,
        organization: Organization,
        *,
        action: str,
    ) -> None:
        actor_role = role_value(actor.role)
        target_role = role_value(target.role)
        if actor.user_id == target.user_id and action in {"delete", "suspend", "grant_admin"}:
            code = "CANNOT_DELETE_SELF" if action == "delete" else "FORBIDDEN"
            raise DomainError(code, "自分自身に対するこの操作は許可されていません。", status.HTTP_403_FORBIDDEN)
        if target_role == OrganizationRole.OWNER and actor_role != OrganizationRole.OWNER:
            raise DomainError("CANNOT_MODIFY_OWNER", "OWNERを変更できません。", status.HTTP_403_FORBIDDEN)
        if (
            target_role == OrganizationRole.ADMIN
            and actor_role == OrganizationRole.ADMIN
            and not organization.allow_admin_manage_admins
        ):
            raise DomainError(
                "FORBIDDEN", "他のADMINを操作することは組織設定で禁止されています。", status.HTTP_403_FORBIDDEN
            )

    @staticmethod
    def require_role_change_allowed(
        actor: OrganizationMember,
        target: OrganizationMember,
        new_role: OrganizationRole,
        organization: Organization,
    ) -> None:
        OrganizationUserPolicy.require_can_manage(actor, target, organization, action="change_role")
        actor_role = role_value(actor.role)
        current_role = role_value(target.role)
        if actor.user_id == target.user_id and new_role in {OrganizationRole.ADMIN, OrganizationRole.OWNER}:
            raise DomainError("FORBIDDEN", "自分自身へ管理権限を付与できません。", status.HTTP_403_FORBIDDEN)
        if new_role == OrganizationRole.OWNER:
            raise DomainError(
                "FORBIDDEN", "OWNERへの変更には所有権移譲APIを使用してください。", status.HTTP_403_FORBIDDEN
            )
        if new_role == OrganizationRole.ADMIN and actor_role != OrganizationRole.OWNER:
            raise DomainError("FORBIDDEN", "ADMIN権限を付与できるのはOWNERだけです。", status.HTTP_403_FORBIDDEN)
        if current_role == OrganizationRole.ADMIN and new_role != OrganizationRole.ADMIN:
            if actor_role != OrganizationRole.OWNER and not organization.allow_admin_manage_admins:
                raise DomainError("FORBIDDEN", "ADMIN権限を解除できません。", status.HTTP_403_FORBIDDEN)

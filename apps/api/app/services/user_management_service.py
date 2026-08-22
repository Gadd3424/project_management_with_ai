import hashlib
import hmac
import secrets
from datetime import UTC, datetime

from fastapi import Request, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import get_settings
from ..domain.permissions import OrganizationPermission
from ..domain.roles import MembershipStatus, OrganizationRole, UserStatus
from ..errors import DomainError
from ..models import OrganizationMember, OutboxEvent, User, UserInvitation, new_id
from ..policies.organization_user_policy import OrganizationUserPolicy
from ..security import hash_password
from ..user_management_schemas import DirectUserCreate, RoleChange, StateChange, UserUpdate
from .audit_service import add_management_audit
from .authorization_service import AuthorizationService, role_value


class UserManagementService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.authorization = AuthorizationService(db)

    @staticmethod
    def temporary_password(user_id: str) -> str:
        digest = hmac.new(
            get_settings().jwt_secret.encode(),
            f"temporary-password:{user_id}".encode(),
            hashlib.sha256,
        ).hexdigest()
        return f"{digest[:20]}Aa1!"

    async def create_direct(
        self, actor: User, organization_id: str, payload: DirectUserCreate, request: Request
    ) -> tuple[OrganizationMember, User, str]:
        actor_member = await self.authorization.require_permission(
            actor, organization_id, OrganizationPermission.USERS_CREATE
        )
        organization = await self.authorization.lock_organization(organization_id)
        if not organization.allow_direct_user_creation:
            raise DomainError(
                "DIRECT_USER_CREATION_DISABLED",
                "この組織では直接登録が許可されていません。",
                status.HTTP_403_FORBIDDEN,
            )
        if payload.role == OrganizationRole.OWNER:
            raise DomainError("INVALID_ROLE", "OWNERは直接付与できません。", status.HTTP_400_BAD_REQUEST)
        if payload.role == OrganizationRole.ADMIN and role_value(actor_member.role) != OrganizationRole.OWNER:
            raise DomainError("FORBIDDEN", "ADMINを登録できるのはOWNERだけです。", status.HTTP_403_FORBIDDEN)
        if await self.db.scalar(select(User.id).where(User.email == payload.email)):
            raise DomainError("USER_ALREADY_EXISTS", "ユーザーを登録できません。", status.HTTP_409_CONFLICT)
        user_id = new_id()
        password = self.temporary_password(user_id)
        now = datetime.now(UTC)
        user = User(
            id=user_id,
            email=payload.email,
            display_name=payload.display_name,
            password_hash=hash_password(password),
            status=UserStatus.ACTIVE,
            is_active=True,
            is_email_verified=False,
            force_password_change=True,
        )
        member = OrganizationMember(
            organization_id=organization_id,
            user_id=user.id,
            role=payload.role,
            status=MembershipStatus.ACTIVE,
            invited_by=actor.id,
            invited_at=now,
            joined_at=now,
        )
        self.db.add_all([user, member])
        self.db.add(
            OutboxEvent(
                organization_id=organization_id,
                event_type="user.direct_registration.created",
                payload={"user_id": user.id, "email": user.email},
            )
        )
        add_management_audit(
            self.db,
            request,
            organization_id,
            actor,
            "user.create",
            user.id,
            new_values={"email": user.email, "role": payload.role.value, "force_password_change": True},
        )
        await self.db.commit()
        await self.db.refresh(member)
        return member, user, password

    async def target_member(
        self, organization_id: str, user_id: str, *, include_deleted: bool = False, lock: bool = False
    ) -> tuple[OrganizationMember, User]:
        query = (
            select(OrganizationMember, User)
            .join(User, User.id == OrganizationMember.user_id)
            .where(
                OrganizationMember.organization_id == organization_id,
                OrganizationMember.user_id == user_id,
            )
        )
        if not include_deleted:
            query = query.where(
                OrganizationMember.deleted_at.is_(None),
                OrganizationMember.status != MembershipStatus.DELETED,
            )
        if lock:
            query = query.with_for_update()
        row = (await self.db.execute(query)).first()
        if not row:
            raise DomainError("USER_NOT_FOUND", "ユーザーが見つかりません。", status.HTTP_404_NOT_FOUND)
        return row[0], row[1]

    async def update(
        self, actor: User, organization_id: str, user_id: str, payload: UserUpdate, request: Request
    ) -> tuple[OrganizationMember, User]:
        actor_member = await self.authorization.require_permission(
            actor, organization_id, OrganizationPermission.USERS_UPDATE
        )
        organization = await self.authorization.lock_organization(organization_id)
        target, user = await self.target_member(organization_id, user_id, lock=True)
        OrganizationUserPolicy.require_can_manage(actor_member, target, organization, action="update")
        self._version(target, payload.version)
        previous = {"display_name": user.display_name}
        user.display_name = payload.display_name
        target.version += 1
        add_management_audit(
            self.db,
            request,
            organization_id,
            actor,
            "user.update",
            user.id,
            previous_values=previous,
            new_values={"display_name": user.display_name},
        )
        await self.db.commit()
        return target, user

    async def change_role(
        self, actor: User, organization_id: str, user_id: str, payload: RoleChange, request: Request
    ) -> tuple[OrganizationMember, User]:
        actor_member = await self.authorization.require_permission(
            actor, organization_id, OrganizationPermission.USERS_CHANGE_ROLE
        )
        organization = await self.authorization.lock_organization(organization_id)
        target, user = await self.target_member(organization_id, user_id, lock=True)
        self._version(target, payload.version)
        OrganizationUserPolicy.require_role_change_allowed(actor_member, target, payload.role, organization)
        current = role_value(target.role)
        if payload.role == OrganizationRole.ADMIN and current != OrganizationRole.ADMIN:
            await self.authorization.require_permission(
                actor, organization_id, OrganizationPermission.USERS_GRANT_ADMIN
            )
        if current == OrganizationRole.ADMIN and payload.role != OrganizationRole.ADMIN:
            await self.authorization.require_permission(
                actor, organization_id, OrganizationPermission.USERS_REVOKE_ADMIN
            )
        if current == OrganizationRole.OWNER and payload.role != OrganizationRole.OWNER:
            await self._require_not_last_owner(organization_id)
        target.role = payload.role
        target.version += 1
        user.auth_version += 1
        action = "user.role.change"
        if payload.role == OrganizationRole.ADMIN:
            action = "user.admin.grant"
        elif current == OrganizationRole.ADMIN:
            action = "user.admin.revoke"
        add_management_audit(
            self.db,
            request,
            organization_id,
            actor,
            action,
            user.id,
            previous_values={"role": current.value},
            new_values={"role": payload.role.value},
            reason=payload.reason,
        )
        await self.db.commit()
        return target, user

    async def suspend(
        self, actor: User, organization_id: str, user_id: str, payload: StateChange, request: Request
    ) -> tuple[OrganizationMember, User]:
        actor_member = await self.authorization.require_permission(
            actor, organization_id, OrganizationPermission.USERS_DEACTIVATE
        )
        organization = await self.authorization.lock_organization(organization_id)
        target, user = await self.target_member(organization_id, user_id, lock=True)
        OrganizationUserPolicy.require_can_manage(actor_member, target, organization, action="suspend")
        self._version(target, payload.version)
        if target.status == MembershipStatus.SUSPENDED:
            raise DomainError("USER_ALREADY_SUSPENDED", "既に利用停止中です。", status.HTTP_409_CONFLICT)
        if role_value(target.role) == OrganizationRole.OWNER:
            await self._require_not_last_owner(organization_id)
        target.status = MembershipStatus.SUSPENDED
        target.suspended_at = datetime.now(UTC)
        target.suspended_by = actor.id
        target.version += 1
        user.auth_version += 1
        await self._sync_user_status(user)
        add_management_audit(
            self.db,
            request,
            organization_id,
            actor,
            "user.suspend",
            user.id,
            previous_values={"status": "active"},
            new_values={"status": "suspended"},
            reason=payload.reason,
        )
        await self.db.commit()
        return target, user

    async def activate(
        self, actor: User, organization_id: str, user_id: str, version: int, request: Request
    ) -> tuple[OrganizationMember, User]:
        actor_member = await self.authorization.require_permission(
            actor, organization_id, OrganizationPermission.USERS_UPDATE
        )
        organization = await self.authorization.lock_organization(organization_id)
        target, user = await self.target_member(organization_id, user_id, lock=True)
        OrganizationUserPolicy.require_can_manage(actor_member, target, organization, action="activate")
        self._version(target, version)
        if target.status != MembershipStatus.SUSPENDED:
            raise DomainError("VERSION_CONFLICT", "利用停止中のユーザーではありません。", status.HTTP_409_CONFLICT)
        target.status = MembershipStatus.ACTIVE
        target.suspended_at = None
        target.suspended_by = None
        target.version += 1
        user.status = UserStatus.ACTIVE
        user.is_active = True
        user.auth_version += 1
        add_management_audit(
            self.db,
            request,
            organization_id,
            actor,
            "user.activate",
            user.id,
            previous_values={"status": "suspended"},
            new_values={"status": "active"},
        )
        await self.db.commit()
        return target, user

    async def delete(
        self, actor: User, organization_id: str, user_id: str, payload: StateChange, request: Request
    ) -> None:
        actor_member = await self.authorization.require_permission(
            actor, organization_id, OrganizationPermission.USERS_DELETE
        )
        organization = await self.authorization.lock_organization(organization_id)
        target, user = await self.target_member(organization_id, user_id, include_deleted=True, lock=True)
        if target.status == MembershipStatus.DELETED or target.deleted_at:
            raise DomainError("USER_ALREADY_DELETED", "既に削除されています。", status.HTTP_409_CONFLICT)
        OrganizationUserPolicy.require_can_manage(actor_member, target, organization, action="delete")
        self._version(target, payload.version)
        if role_value(target.role) == OrganizationRole.OWNER:
            await self._require_not_last_owner(organization_id)
        now = datetime.now(UTC)
        target.status = MembershipStatus.DELETED
        target.deleted_at = now
        target.deleted_by = actor.id
        target.version += 1
        user.auth_version += 1
        await self.db.execute(
            UserInvitation.__table__.update()
            .where(
                UserInvitation.organization_id == organization_id,
                UserInvitation.email == user.email,
                UserInvitation.accepted_at.is_(None),
                UserInvitation.revoked_at.is_(None),
            )
            .values(revoked_at=now)
        )
        await self._sync_user_status(user)
        add_management_audit(
            self.db,
            request,
            organization_id,
            actor,
            "user.delete",
            user.id,
            previous_values={"status": "active"},
            new_values={"status": "deleted"},
            reason=payload.reason,
        )
        await self.db.commit()

    async def restore(
        self, actor: User, organization_id: str, user_id: str, version: int, reason: str, request: Request
    ) -> tuple[OrganizationMember, User]:
        actor_member = await self.authorization.require_permission(
            actor, organization_id, OrganizationPermission.USERS_RESTORE
        )
        organization = await self.authorization.lock_organization(organization_id)
        target, user = await self.target_member(organization_id, user_id, include_deleted=True, lock=True)
        OrganizationUserPolicy.require_can_manage(actor_member, target, organization, action="restore")
        self._version(target, version)
        if target.status != MembershipStatus.DELETED:
            raise DomainError("USER_NOT_DELETED", "削除済みユーザーではありません。", status.HTTP_409_CONFLICT)
        target.status = MembershipStatus.ACTIVE
        target.deleted_at = None
        target.deleted_by = None
        target.version += 1
        user.status = UserStatus.ACTIVE
        user.is_active = True
        user.deleted_at = None
        user.auth_version += 1
        add_management_audit(
            self.db,
            request,
            organization_id,
            actor,
            "user.restore",
            user.id,
            previous_values={"status": "deleted"},
            new_values={"status": "active"},
            reason=reason,
        )
        await self.db.commit()
        return target, user

    async def request_password_reset(self, actor: User, organization_id: str, user_id: str, request: Request) -> None:
        actor_member = await self.authorization.require_permission(
            actor, organization_id, OrganizationPermission.USERS_RESET_PASSWORD
        )
        organization = await self.authorization.lock_organization(organization_id)
        target, user = await self.target_member(organization_id, user_id)
        OrganizationUserPolicy.require_can_manage(actor_member, target, organization, action="request_password_reset")
        self.db.add(
            OutboxEvent(
                organization_id=organization_id,
                event_type="user.password_reset.requested",
                payload={"user_id": user.id, "email": user.email},
            )
        )
        add_management_audit(self.db, request, organization_id, actor, "user.password_reset.request", user.id)
        await self.db.commit()

    async def purge(self, actor: User, organization_id: str, user_id: str, request: Request) -> None:
        await self.authorization.require_permission(actor, organization_id, OrganizationPermission.USERS_PURGE)
        await self.authorization.lock_organization(organization_id)
        target, user = await self.target_member(organization_id, user_id, include_deleted=True, lock=True)
        if target.status != MembershipStatus.DELETED:
            raise DomainError("USER_NOT_DELETED", "先に論理削除してください。", status.HTTP_409_CONFLICT)
        other_memberships = await self.db.scalar(
            select(func.count())
            .select_from(OrganizationMember)
            .where(
                OrganizationMember.user_id == user.id,
                OrganizationMember.organization_id != organization_id,
                OrganizationMember.status != MembershipStatus.DELETED,
            )
        )
        if other_memberships:
            raise DomainError("FORBIDDEN", "他組織に所属するユーザーは匿名化できません。", status.HTTP_409_CONFLICT)
        previous = {"email": user.email, "display_name": user.display_name}
        user.email = f"deleted-{user.id}@invalid.local"
        user.display_name = "削除済みユーザー"
        user.password_hash = hash_password(secrets.token_urlsafe(48))
        user.status = UserStatus.DELETED
        user.is_active = False
        user.auth_version += 1
        add_management_audit(
            self.db,
            request,
            organization_id,
            actor,
            "user.purge",
            user.id,
            previous_values=previous,
            new_values={"anonymized": True},
        )
        await self.db.commit()

    async def _require_not_last_owner(self, organization_id: str) -> None:
        count = await self.db.scalar(
            select(func.count())
            .select_from(OrganizationMember)
            .where(
                OrganizationMember.organization_id == organization_id,
                OrganizationMember.role == OrganizationRole.OWNER,
                OrganizationMember.status == MembershipStatus.ACTIVE,
                OrganizationMember.deleted_at.is_(None),
            )
        )
        if int(count or 0) <= 1:
            raise DomainError(
                "LAST_OWNER_CANNOT_BE_REMOVED",
                "組織に所属する最後の所有者は変更できません。",
                status.HTTP_409_CONFLICT,
            )

    async def _sync_user_status(self, user: User) -> None:
        await self.db.flush()
        active_count = await self.db.scalar(
            select(func.count())
            .select_from(OrganizationMember)
            .where(
                OrganizationMember.user_id == user.id,
                OrganizationMember.status == MembershipStatus.ACTIVE,
                OrganizationMember.deleted_at.is_(None),
            )
        )
        if not active_count:
            remaining_count = await self.db.scalar(
                select(func.count())
                .select_from(OrganizationMember)
                .where(
                    OrganizationMember.user_id == user.id,
                    OrganizationMember.status != MembershipStatus.DELETED,
                    OrganizationMember.deleted_at.is_(None),
                )
            )
            user.status = UserStatus.SUSPENDED if remaining_count else UserStatus.DELETED
            user.is_active = False

    @staticmethod
    def _version(member: OrganizationMember, expected: int) -> None:
        if member.version != expected:
            raise DomainError("VERSION_CONFLICT", "他のユーザーによって更新されています。", status.HTTP_409_CONFLICT)

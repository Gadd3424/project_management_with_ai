import hashlib
import hmac
from datetime import UTC, datetime, timedelta

from fastapi import Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import get_settings
from ..domain.permissions import OrganizationPermission
from ..domain.roles import MembershipStatus, OrganizationRole, UserStatus
from ..errors import DomainError
from ..models import OrganizationMember, OutboxEvent, User, UserInvitation, new_id
from ..security import hash_password
from ..user_management_schemas import InvitationAccept, InvitationCreate
from .audit_service import add_management_audit
from .authorization_service import AuthorizationService, role_value


def invitation_token(invitation_id: str) -> str:
    secret = get_settings().jwt_secret.encode()
    return hmac.new(secret, f"invitation:{invitation_id}".encode(), hashlib.sha256).hexdigest()


def invitation_token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


class InvitationService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.authorization = AuthorizationService(db)

    async def create(
        self, actor: User, organization_id: str, payload: InvitationCreate, request: Request
    ) -> tuple[UserInvitation, str]:
        actor_member = await self.authorization.require_permission(
            actor, organization_id, OrganizationPermission.USERS_CREATE
        )
        actor_role = role_value(actor_member.role)
        if payload.role == OrganizationRole.OWNER:
            raise DomainError("INVALID_ROLE", "OWNERは招待で付与できません。", status.HTTP_400_BAD_REQUEST)
        if payload.role == OrganizationRole.ADMIN and actor_role != OrganizationRole.OWNER:
            raise DomainError("FORBIDDEN", "ADMINを招待できるのはOWNERだけです。", status.HTTP_403_FORBIDDEN)
        existing_user = await self.db.scalar(select(User).where(User.email == payload.email))
        if existing_user:
            member = await self.db.scalar(
                select(OrganizationMember).where(
                    OrganizationMember.organization_id == organization_id,
                    OrganizationMember.user_id == existing_user.id,
                )
            )
            if member:
                raise DomainError(
                    "USER_ALREADY_EXISTS", "この組織にユーザーが既に存在します。", status.HTTP_409_CONFLICT
                )
        now = datetime.now(UTC)
        existing_invitation = await self.db.scalar(
            select(UserInvitation).where(
                UserInvitation.organization_id == organization_id,
                UserInvitation.email == payload.email,
                UserInvitation.accepted_at.is_(None),
                UserInvitation.revoked_at.is_(None),
                UserInvitation.expires_at > now,
            )
        )
        if existing_invitation:
            raise DomainError("INVITATION_ALREADY_EXISTS", "有効な招待が既に存在します。", status.HTTP_409_CONFLICT)
        organization = await self.authorization.lock_organization(organization_id)
        invitation_id = new_id()
        token = invitation_token(invitation_id)
        invitation = UserInvitation(
            id=invitation_id,
            organization_id=organization_id,
            email=payload.email,
            display_name=payload.display_name,
            role=payload.role,
            token_hash=invitation_token_hash(token),
            invited_by=actor.id,
            expires_at=now + timedelta(hours=organization.invitation_expiry_hours),
        )
        self.db.add(invitation)
        await self.db.flush()
        self.db.add(
            OutboxEvent(
                organization_id=organization_id,
                event_type="user.invitation.created",
                payload={"invitation_id": invitation.id, "email": invitation.email},
            )
        )
        add_management_audit(
            self.db,
            request,
            organization_id,
            actor,
            "user.invitation.create",
            None,
            new_values={"email": invitation.email, "role": invitation.role.value},
        )
        await self.db.commit()
        await self.db.refresh(invitation)
        return invitation, token

    async def resend(
        self, actor: User, organization_id: str, invitation_id: str, request: Request
    ) -> tuple[UserInvitation, str]:
        await self.authorization.require_permission(
            actor, organization_id, OrganizationPermission.USERS_RESEND_INVITATION
        )
        invitation = await self._get(organization_id, invitation_id)
        if invitation.accepted_at or invitation.revoked_at:
            raise DomainError("INVITATION_REVOKED", "この招待は再送できません。", status.HTTP_409_CONFLICT)
        organization = await self.authorization.lock_organization(organization_id)
        invitation.expires_at = datetime.now(UTC) + timedelta(hours=organization.invitation_expiry_hours)
        invitation.version += 1
        token = invitation_token(invitation.id)
        invitation.token_hash = invitation_token_hash(token)
        self.db.add(
            OutboxEvent(
                organization_id=organization_id,
                event_type="user.invitation.resent",
                payload={"invitation_id": invitation.id, "email": invitation.email},
            )
        )
        add_management_audit(
            self.db,
            request,
            organization_id,
            actor,
            "user.invitation.resend",
            None,
            new_values={"email": invitation.email},
        )
        await self.db.commit()
        await self.db.refresh(invitation)
        return invitation, token

    async def revoke(self, actor: User, organization_id: str, invitation_id: str, request: Request) -> None:
        await self.authorization.require_permission(actor, organization_id, OrganizationPermission.USERS_CREATE)
        invitation = await self._get(organization_id, invitation_id)
        if invitation.accepted_at:
            raise DomainError("INVITATION_REVOKED", "受諾済みの招待です。", status.HTTP_409_CONFLICT)
        invitation.revoked_at = datetime.now(UTC)
        invitation.version += 1
        add_management_audit(
            self.db,
            request,
            organization_id,
            actor,
            "user.invitation.revoke",
            None,
            previous_values={"email": invitation.email},
        )
        await self.db.commit()

    async def accept(self, payload: InvitationAccept, request: Request) -> tuple[User, OrganizationMember]:
        token_hash = invitation_token_hash(payload.token)
        invitation = await self.db.scalar(
            select(UserInvitation).where(UserInvitation.token_hash == token_hash).with_for_update()
        )
        now = datetime.now(UTC)
        if not invitation:
            raise DomainError("INVITATION_REVOKED", "招待を利用できません。", status.HTTP_400_BAD_REQUEST)
        if invitation.revoked_at:
            raise DomainError("INVITATION_REVOKED", "招待は取り消されています。", status.HTTP_409_CONFLICT)
        if invitation.accepted_at:
            raise DomainError("INVITATION_REVOKED", "招待は既に使用されています。", status.HTTP_409_CONFLICT)
        expires_at = invitation.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=UTC)
        if expires_at <= now:
            raise DomainError("INVITATION_EXPIRED", "招待の有効期限が切れています。", status.HTTP_409_CONFLICT)
        await self.authorization.lock_organization(invitation.organization_id)
        user = await self.db.scalar(select(User).where(User.email == invitation.email).with_for_update())
        if user:
            duplicate = await self.db.scalar(
                select(OrganizationMember).where(
                    OrganizationMember.organization_id == invitation.organization_id,
                    OrganizationMember.user_id == user.id,
                )
            )
            if duplicate:
                raise DomainError("USER_ALREADY_EXISTS", "ユーザーは既に所属しています。", status.HTTP_409_CONFLICT)
            user.display_name = payload.display_name
            user.password_hash = hash_password(payload.password)
            user.status = UserStatus.ACTIVE
            user.is_active = True
            user.is_email_verified = True
            user.password_changed_at = now
            user.auth_version += 1
        else:
            user = User(
                email=invitation.email,
                display_name=payload.display_name,
                password_hash=hash_password(payload.password),
                status=UserStatus.ACTIVE,
                is_active=True,
                is_email_verified=True,
                password_changed_at=now,
            )
            self.db.add(user)
            await self.db.flush()
        member = OrganizationMember(
            organization_id=invitation.organization_id,
            user_id=user.id,
            role=invitation.role,
            status=MembershipStatus.ACTIVE,
            invited_by=invitation.invited_by,
            invited_at=invitation.created_at,
            joined_at=now,
        )
        self.db.add(member)
        invitation.accepted_at = now
        invitation.version += 1
        add_management_audit(
            self.db,
            request,
            invitation.organization_id,
            user,
            "user.invitation.accept",
            user.id,
            new_values={"email": user.email, "role": invitation.role.value},
        )
        await self.db.commit()
        await self.db.refresh(member)
        return user, member

    async def _get(self, organization_id: str, invitation_id: str) -> UserInvitation:
        invitation = await self.db.scalar(
            select(UserInvitation).where(
                UserInvitation.id == invitation_id,
                UserInvitation.organization_id == organization_id,
            )
        )
        if not invitation:
            raise DomainError("USER_NOT_FOUND", "招待が見つかりません。", status.HTTP_404_NOT_FOUND)
        return invitation

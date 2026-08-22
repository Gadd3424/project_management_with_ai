from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import asc, desc, func, or_, select

from ..config import get_settings
from ..dependencies import Csrf, CurrentUser, DbSession
from ..domain.permissions import OrganizationPermission, permissions_for_role
from ..domain.roles import MembershipStatus, OrganizationRole
from ..models import AuditLog, OrganizationMember, User, UserInvitation
from ..rate_limit import limit_admin_mutation, limit_invitation_accept
from ..services.authorization_service import AuthorizationService
from ..services.invitation_service import InvitationService
from ..services.ownership_service import OwnershipService
from ..services.user_management_service import UserManagementService
from ..user_management_schemas import (
    DirectUserCreate,
    DirectUserRead,
    InvitationAccept,
    InvitationCreate,
    InvitationRead,
    OrganizationUserPage,
    OrganizationUserRead,
    OwnershipTransfer,
    PermissionRead,
    RestoreRequest,
    RoleChange,
    StateChange,
    UserUpdate,
)

router = APIRouter(tags=["organization users"])


def user_read(member: OrganizationMember, user: User) -> OrganizationUserRead:
    deleted = member.status == MembershipStatus.DELETED
    return OrganizationUserRead(
        id=user.id,
        email=user.email,
        display_name="削除済みユーザー" if deleted else user.display_name,
        role=member.role,
        status=member.status,
        last_login_at=user.last_login_at,
        created_at=member.created_at,
        version=member.version,
        deleted_at=member.deleted_at,
    )


@router.get("/organizations/{organization_id}/me/permissions", response_model=PermissionRead)
async def my_permissions(organization_id: str, user: CurrentUser, db: DbSession) -> PermissionRead:
    member = await AuthorizationService(db).get_member(user.id, organization_id)
    return PermissionRead(
        role=member.role,
        permissions=sorted(permission.value for permission in permissions_for_role(member.role)),
    )


@router.get("/organizations/{organization_id}/users", response_model=OrganizationUserPage)
async def list_users(
    organization_id: str,
    user: CurrentUser,
    db: DbSession,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    search: str | None = Query(None, max_length=120),
    role: OrganizationRole | None = None,
    member_status: MembershipStatus | None = Query(None, alias="status"),
    sort: str = Query("-created_at", pattern="^-?(created_at|email|display_name)$"),
    include_deleted: bool = False,
) -> OrganizationUserPage:
    await AuthorizationService(db).require_permission(user, organization_id, OrganizationPermission.USERS_READ)
    filters = [OrganizationMember.organization_id == organization_id]
    if not include_deleted:
        filters += [OrganizationMember.deleted_at.is_(None), OrganizationMember.status != MembershipStatus.DELETED]
    if search:
        term = f"%{search.strip()}%"
        filters.append(or_(User.email.ilike(term), User.display_name.ilike(term)))
    if role:
        filters.append(OrganizationMember.role == role)
    if member_status:
        filters.append(OrganizationMember.status == member_status)
    field_name = sort.lstrip("-")
    fields = {"created_at": OrganizationMember.created_at, "email": User.email, "display_name": User.display_name}
    order = desc(fields[field_name]) if sort.startswith("-") else asc(fields[field_name])
    total = await db.scalar(
        select(func.count())
        .select_from(OrganizationMember)
        .join(User, User.id == OrganizationMember.user_id)
        .where(*filters)
    )
    rows = (
        await db.execute(
            select(OrganizationMember, User)
            .join(User, User.id == OrganizationMember.user_id)
            .where(*filters)
            .order_by(order, OrganizationMember.id)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).all()
    return OrganizationUserPage(
        items=[user_read(member, target) for member, target in rows],
        page=page,
        page_size=page_size,
        total=int(total or 0),
    )


@router.get("/organizations/{organization_id}/users/{user_id}", response_model=OrganizationUserRead)
async def get_user(organization_id: str, user_id: str, user: CurrentUser, db: DbSession):
    await AuthorizationService(db).require_permission(user, organization_id, OrganizationPermission.USERS_READ)
    member, target = await UserManagementService(db).target_member(organization_id, user_id, include_deleted=True)
    return user_read(member, target)


@router.get("/organizations/{organization_id}/users/invitations/pending", response_model=list[InvitationRead])
async def pending_invitations(organization_id: str, user: CurrentUser, db: DbSession):
    await AuthorizationService(db).require_permission(user, organization_id, OrganizationPermission.USERS_READ)
    invitations = (
        await db.scalars(
            select(UserInvitation)
            .where(
                UserInvitation.organization_id == organization_id,
                UserInvitation.accepted_at.is_(None),
                UserInvitation.revoked_at.is_(None),
            )
            .order_by(UserInvitation.created_at.desc())
        )
    ).all()
    return [InvitationRead(**invitation.__dict__) for invitation in invitations]


@router.post("/organizations/{organization_id}/users/invitations", response_model=InvitationRead, status_code=201)
async def invite_user(
    organization_id: str,
    payload: InvitationCreate,
    request: Request,
    user: CurrentUser,
    db: DbSession,
    _: Csrf,
    __: None = Depends(limit_admin_mutation),
):
    invitation, token = await InvitationService(db).create(user, organization_id, payload, request)
    development_token = token if get_settings().app_env == "development" else None
    return InvitationRead(**invitation.__dict__, development_token=development_token)


@router.post("/organizations/{organization_id}/users/direct", response_model=DirectUserRead, status_code=201)
async def create_user_directly(
    organization_id: str,
    payload: DirectUserCreate,
    request: Request,
    user: CurrentUser,
    db: DbSession,
    _: Csrf,
    __: None = Depends(limit_admin_mutation),
):
    _, target, password = await UserManagementService(db).create_direct(user, organization_id, payload, request)
    development_password = password if get_settings().app_env == "development" else None
    return DirectUserRead(user_id=target.id, temporary_password=development_password)


@router.post("/organizations/{organization_id}/users/invitations/{invitation_id}/resend", response_model=InvitationRead)
async def resend_invitation(
    organization_id: str,
    invitation_id: str,
    request: Request,
    user: CurrentUser,
    db: DbSession,
    _: Csrf,
    __: None = Depends(limit_admin_mutation),
):
    invitation, token = await InvitationService(db).resend(user, organization_id, invitation_id, request)
    development_token = token if get_settings().app_env == "development" else None
    return InvitationRead(**invitation.__dict__, development_token=development_token)


@router.post("/organizations/{organization_id}/users/invitations/{invitation_id}/revoke", status_code=204)
async def revoke_invitation(
    organization_id: str,
    invitation_id: str,
    request: Request,
    user: CurrentUser,
    db: DbSession,
    _: Csrf,
    __: None = Depends(limit_admin_mutation),
):
    await InvitationService(db).revoke(user, organization_id, invitation_id, request)


@router.post("/auth/invitations/accept", status_code=201)
async def accept_invitation(
    payload: InvitationAccept,
    request: Request,
    db: DbSession,
    _: None = Depends(limit_invitation_accept),
):
    user, member = await InvitationService(db).accept(payload, request)
    return {"user_id": user.id, "organization_id": member.organization_id}


@router.patch("/organizations/{organization_id}/users/{user_id}", response_model=OrganizationUserRead)
async def update_user(
    organization_id: str,
    user_id: str,
    payload: UserUpdate,
    request: Request,
    user: CurrentUser,
    db: DbSession,
    _: Csrf,
    __: None = Depends(limit_admin_mutation),
):
    member, target = await UserManagementService(db).update(user, organization_id, user_id, payload, request)
    return user_read(member, target)


@router.patch("/organizations/{organization_id}/users/{user_id}/role", response_model=OrganizationUserRead)
async def change_role(
    organization_id: str,
    user_id: str,
    payload: RoleChange,
    request: Request,
    user: CurrentUser,
    db: DbSession,
    _: Csrf,
    __: None = Depends(limit_admin_mutation),
):
    member, target = await UserManagementService(db).change_role(user, organization_id, user_id, payload, request)
    return user_read(member, target)


@router.post("/organizations/{organization_id}/users/{user_id}/suspend", response_model=OrganizationUserRead)
async def suspend_user(
    organization_id: str,
    user_id: str,
    payload: StateChange,
    request: Request,
    user: CurrentUser,
    db: DbSession,
    _: Csrf,
    __: None = Depends(limit_admin_mutation),
):
    member, target = await UserManagementService(db).suspend(user, organization_id, user_id, payload, request)
    return user_read(member, target)


@router.post("/organizations/{organization_id}/users/{user_id}/activate", response_model=OrganizationUserRead)
async def activate_user(
    organization_id: str,
    user_id: str,
    payload: RestoreRequest,
    request: Request,
    user: CurrentUser,
    db: DbSession,
    _: Csrf,
    __: None = Depends(limit_admin_mutation),
):
    member, target = await UserManagementService(db).activate(user, organization_id, user_id, payload.version, request)
    return user_read(member, target)


@router.post("/organizations/{organization_id}/users/{user_id}/delete", status_code=204)
async def delete_user(
    organization_id: str,
    user_id: str,
    payload: StateChange,
    request: Request,
    user: CurrentUser,
    db: DbSession,
    _: Csrf,
    __: None = Depends(limit_admin_mutation),
):
    await UserManagementService(db).delete(user, organization_id, user_id, payload, request)


@router.post("/organizations/{organization_id}/users/{user_id}/restore", response_model=OrganizationUserRead)
async def restore_user(
    organization_id: str,
    user_id: str,
    payload: RestoreRequest,
    request: Request,
    user: CurrentUser,
    db: DbSession,
    _: Csrf,
    __: None = Depends(limit_admin_mutation),
):
    member, target = await UserManagementService(db).restore(
        user, organization_id, user_id, payload.version, payload.reason, request
    )
    return user_read(member, target)


@router.post("/organizations/{organization_id}/users/{user_id}/request-password-reset", status_code=202)
async def request_password_reset(
    organization_id: str,
    user_id: str,
    request: Request,
    user: CurrentUser,
    db: DbSession,
    _: Csrf,
    __: None = Depends(limit_admin_mutation),
):
    await UserManagementService(db).request_password_reset(user, organization_id, user_id, request)


@router.post("/organizations/{organization_id}/users/{user_id}/purge", status_code=204)
async def purge_user(
    organization_id: str,
    user_id: str,
    request: Request,
    user: CurrentUser,
    db: DbSession,
    _: Csrf,
    __: None = Depends(limit_admin_mutation),
):
    await UserManagementService(db).purge(user, organization_id, user_id, request)


@router.post("/organizations/{organization_id}/ownership/transfer", status_code=204)
async def transfer_ownership(
    organization_id: str,
    payload: OwnershipTransfer,
    request: Request,
    user: CurrentUser,
    db: DbSession,
    _: Csrf,
    __: None = Depends(limit_admin_mutation),
):
    await OwnershipService(db).transfer(
        user, organization_id, payload.new_owner_user_id, payload.current_user_password, request
    )


@router.get("/organizations/{organization_id}/user-management/audit-logs")
async def user_management_audit(
    organization_id: str, user: CurrentUser, db: DbSession, limit: int = Query(100, ge=1, le=200)
):
    await AuthorizationService(db).require_permission(user, organization_id, OrganizationPermission.AUDIT_LOGS_READ)
    rows = (
        await db.scalars(
            select(AuditLog)
            .where(
                AuditLog.organization_id == organization_id,
                or_(AuditLog.action.startswith("user."), AuditLog.action == "organization.ownership.transfer"),
            )
            .order_by(AuditLog.created_at.desc())
            .limit(limit)
        )
    ).all()
    return [
        {
            "id": row.id,
            "actor_user_id": row.actor_id,
            "target_user_id": row.target_user_id,
            "action": row.action,
            "previous_values": row.previous_values,
            "new_values": row.new_values,
            "reason": row.reason,
            "result": row.result,
            "correlation_id": row.correlation_id,
            "ip_address": row.ip_address,
            "user_agent": row.user_agent,
            "created_at": row.created_at,
        }
        for row in rows
    ]

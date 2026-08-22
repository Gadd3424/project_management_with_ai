from dataclasses import dataclass
from typing import Annotated

import jwt
from fastapi import Cookie, Depends, Header, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .db import get_db
from .domain.roles import MembershipStatus, UserStatus
from .models import OrganizationMember, User
from .security import decode_token_claims

DbSession = Annotated[AsyncSession, Depends(get_db)]
bearer = HTTPBearer(auto_error=False)


async def current_user(
    request: Request,
    db: DbSession,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
    access_token: Annotated[str | None, Cookie()] = None,
) -> User:
    raw_token = credentials.credentials if credentials else access_token
    if not raw_token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Authentication required")
    try:
        claims = decode_token_claims(raw_token, "access")
        user_id = str(claims["sub"])
    except jwt.PyJWTError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid access token") from exc
    user = await db.get(User, user_id)
    if (
        not user
        or not user.is_active
        or user.status != UserStatus.ACTIVE
        or user.deleted_at
        or int(claims.get("auth_version", 0)) != user.auth_version
    ):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Inactive user")
    if user.force_password_change and request.url.path not in {
        "/api/v1/auth/me",
        "/api/v1/auth/change-password",
    }:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "PASSWORD_CHANGE_REQUIRED")
    return user


CurrentUser = Annotated[User, Depends(current_user)]


async def csrf_protect(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
    csrf_cookie: Annotated[str | None, Cookie(alias="csrf_token")] = None,
    csrf_header: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
) -> None:
    if request.method in {"GET", "HEAD", "OPTIONS"} or credentials:
        return
    if not csrf_cookie or not csrf_header or csrf_cookie != csrf_header:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "CSRF validation failed")


@dataclass(frozen=True)
class TenantContext:
    organization_id: str
    role: str
    member_id: str


async def tenant_context(
    db: DbSession,
    user: CurrentUser,
    organization_id: Annotated[str, Header(alias="X-Organization-ID")],
) -> TenantContext:
    member = await db.scalar(
        select(OrganizationMember).where(
            OrganizationMember.organization_id == organization_id,
            OrganizationMember.user_id == user.id,
            OrganizationMember.deleted_at.is_(None),
            OrganizationMember.status == MembershipStatus.ACTIVE,
        )
    )
    if not member:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Organization access denied")
    role = member.role.value if hasattr(member.role, "value") else str(member.role)
    return TenantContext(organization_id, role, member.id)


Tenant = Annotated[TenantContext, Depends(tenant_context)]
Csrf = Annotated[None, Depends(csrf_protect)]


ROLE_RANK = {"viewer": 0, "member": 1, "manager": 2, "admin": 3, "owner": 4}


def require_role(minimum: str):
    async def check(tenant: Tenant) -> TenantContext:
        if ROLE_RANK.get(tenant.role, -1) < ROLE_RANK[minimum]:
            raise HTTPException(status.HTTP_403_FORBIDDEN, f"{minimum} role required")
        return tenant

    return check

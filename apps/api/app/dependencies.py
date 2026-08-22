from dataclasses import dataclass
from typing import Annotated

import jwt
from fastapi import Cookie, Depends, Header, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .db import get_db
from .models import OrganizationMember, User
from .security import decode_token

DbSession = Annotated[AsyncSession, Depends(get_db)]
bearer = HTTPBearer(auto_error=False)


async def current_user(
    db: DbSession,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
    access_token: Annotated[str | None, Cookie()] = None,
) -> User:
    raw_token = credentials.credentials if credentials else access_token
    if not raw_token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Authentication required")
    try:
        user_id = decode_token(raw_token, "access")
    except jwt.PyJWTError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid access token") from exc
    user = await db.get(User, user_id)
    if not user or not user.is_active or user.deleted_at:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Inactive user")
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
        )
    )
    if not member:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Organization access denied")
    return TenantContext(organization_id, member.role)


Tenant = Annotated[TenantContext, Depends(tenant_context)]
Csrf = Annotated[None, Depends(csrf_protect)]


ROLE_RANK = {"viewer": 0, "member": 1, "manager": 2, "admin": 3, "owner": 4}


def require_role(minimum: str):
    async def check(tenant: Tenant) -> TenantContext:
        if ROLE_RANK.get(tenant.role, -1) < ROLE_RANK[minimum]:
            raise HTTPException(status.HTTP_403_FORBIDDEN, f"{minimum} role required")
        return tenant

    return check

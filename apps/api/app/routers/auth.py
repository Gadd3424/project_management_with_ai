from datetime import UTC, datetime, timedelta

import jwt
from fastapi import APIRouter, Cookie, HTTPException, Response, status
from sqlalchemy import select

from ..config import get_settings
from ..dependencies import Csrf, CurrentUser, DbSession
from ..domain.roles import UserStatus
from ..models import User
from ..schemas import LoginRequest, LoginResponse, UserRead
from ..security import create_token, hash_password, new_csrf_token, verify_password
from ..user_management_schemas import ChangePassword

router = APIRouter(prefix="/auth", tags=["auth"])


def set_auth_cookies(response: Response, access: str, refresh: str, csrf: str) -> None:
    settings = get_settings()
    common = {"secure": settings.cookie_secure, "samesite": "lax", "path": "/"}
    response.set_cookie("access_token", access, httponly=True, max_age=900, **common)
    response.set_cookie(
        "refresh_token",
        refresh,
        httponly=True,
        max_age=settings.refresh_token_days * 86400,
        **common,
    )
    response.set_cookie("csrf_token", csrf, httponly=False, max_age=86400, **common)


@router.post("/login", response_model=LoginResponse)
async def login(payload: LoginRequest, response: Response, db: DbSession) -> LoginResponse:
    user = await db.scalar(select(User).where(User.email == payload.email.lower()))
    if (
        not user
        or user.status != UserStatus.ACTIVE
        or not user.is_active
        or not verify_password(payload.password, user.password_hash)
    ):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid credentials")
    settings = get_settings()
    access = create_token(user.id, "access", timedelta(minutes=settings.access_token_minutes), user.auth_version)
    refresh = create_token(user.id, "refresh", timedelta(days=settings.refresh_token_days), user.auth_version)
    user.last_login_at = datetime.now(UTC)
    user.failed_login_count = 0
    await db.commit()
    csrf = new_csrf_token()
    set_auth_cookies(response, access, refresh, csrf)
    return LoginResponse(user=UserRead.model_validate(user), access_token=access, csrf_token=csrf)


@router.post("/refresh", response_model=LoginResponse)
async def refresh(
    response: Response,
    db: DbSession,
    refresh_token: str | None = Cookie(default=None),
) -> LoginResponse:
    if not refresh_token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Refresh token required")
    try:
        from ..security import decode_token_claims

        claims = decode_token_claims(refresh_token, "refresh")
        user_id = str(claims["sub"])
    except jwt.PyJWTError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid refresh token") from exc
    user = await db.get(User, user_id)
    if (
        not user
        or not user.is_active
        or user.status != UserStatus.ACTIVE
        or int(claims.get("auth_version", 0)) != user.auth_version
    ):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Inactive user")
    settings = get_settings()
    access = create_token(user.id, "access", timedelta(minutes=settings.access_token_minutes), user.auth_version)
    new_refresh = create_token(user.id, "refresh", timedelta(days=settings.refresh_token_days), user.auth_version)
    csrf = new_csrf_token()
    set_auth_cookies(response, access, new_refresh, csrf)
    return LoginResponse(user=UserRead.model_validate(user), access_token=access, csrf_token=csrf)


@router.post("/logout", status_code=204)
async def logout(response: Response, _: Csrf) -> None:
    for name in ("access_token", "refresh_token", "csrf_token"):
        response.delete_cookie(name, path="/")


@router.get("/me", response_model=UserRead)
async def me(user: CurrentUser) -> UserRead:
    return UserRead.model_validate(user)


@router.post("/change-password", status_code=204)
async def change_password(payload: ChangePassword, user: CurrentUser, db: DbSession, _: Csrf) -> None:
    if not verify_password(payload.current_password, user.password_hash):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Current password is invalid")
    user.password_hash = hash_password(payload.new_password)
    user.password_changed_at = datetime.now(UTC)
    user.force_password_change = False
    user.auth_version += 1
    await db.commit()

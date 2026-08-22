from datetime import timedelta

import jwt
from fastapi import APIRouter, Cookie, HTTPException, Response, status
from sqlalchemy import select

from ..config import get_settings
from ..dependencies import Csrf, CurrentUser, DbSession
from ..models import User
from ..schemas import LoginRequest, LoginResponse, UserRead
from ..security import create_token, decode_token, new_csrf_token, verify_password

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
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid credentials")
    settings = get_settings()
    access = create_token(user.id, "access", timedelta(minutes=settings.access_token_minutes))
    refresh = create_token(user.id, "refresh", timedelta(days=settings.refresh_token_days))
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
        user_id = decode_token(refresh_token, "refresh")
    except jwt.PyJWTError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid refresh token") from exc
    user = await db.get(User, user_id)
    if not user or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Inactive user")
    settings = get_settings()
    access = create_token(user.id, "access", timedelta(minutes=settings.access_token_minutes))
    new_refresh = create_token(user.id, "refresh", timedelta(days=settings.refresh_token_days))
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

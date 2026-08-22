from typing import Any

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import AuditLog, User

SECRET_KEYS = {"password", "password_hash", "token", "token_hash", "access_token", "refresh_token"}


def sanitize(values: dict[str, Any] | None) -> dict[str, Any]:
    return {key: value for key, value in (values or {}).items() if key.lower() not in SECRET_KEYS}


def add_management_audit(
    db: AsyncSession,
    request: Request,
    organization_id: str,
    actor: User,
    action: str,
    target_user_id: str | None,
    *,
    previous_values: dict[str, Any] | None = None,
    new_values: dict[str, Any] | None = None,
    reason: str | None = None,
    result: str = "success",
) -> None:
    db.add(
        AuditLog(
            organization_id=organization_id,
            actor_id=actor.id,
            action=action,
            resource_type="organization_user",
            resource_id=target_user_id or organization_id,
            target_user_id=target_user_id,
            previous_values=sanitize(previous_values),
            new_values=sanitize(new_values),
            reason=reason,
            result=result,
            correlation_id=getattr(request.state, "correlation_id", "unknown"),
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("User-Agent", "")[:500],
            details={},
        )
    )

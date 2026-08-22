from typing import Any

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from .models import AuditLog, User


def add_audit(
    db: AsyncSession,
    request: Request,
    organization_id: str,
    user: User,
    action: str,
    resource_type: str,
    resource_id: str,
    details: dict[str, Any] | None = None,
) -> None:
    db.add(
        AuditLog(
            organization_id=organization_id,
            actor_id=user.id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            correlation_id=getattr(request.state, "correlation_id", "unknown"),
            details=details or {},
        )
    )

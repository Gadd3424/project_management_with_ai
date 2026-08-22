from fastapi import APIRouter
from sqlalchemy import select

from ..dependencies import DbSession, Tenant
from ..models import AuditLog

router = APIRouter(tags=["audit"])


@router.get("/audit-logs")
async def list_audit_logs(db: DbSession, tenant: Tenant, limit: int = 100) -> list[dict]:
    rows = (
        await db.scalars(
            select(AuditLog)
            .where(AuditLog.organization_id == tenant.organization_id)
            .order_by(AuditLog.created_at.desc())
            .limit(min(max(limit, 1), 200))
        )
    ).all()
    return [
        {
            "id": row.id,
            "actor_id": row.actor_id,
            "action": row.action,
            "resource_type": row.resource_type,
            "resource_id": row.resource_id,
            "correlation_id": row.correlation_id,
            "details": row.details,
            "created_at": row.created_at,
        }
        for row in rows
    ]

import hashlib
import json
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import IdempotencyRecord


def request_digest(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
    return hashlib.sha256(encoded).hexdigest()


async def find_replayed_resource(
    db: AsyncSession,
    organization_id: str,
    key: str | None,
    method: str,
    path: str,
    payload: dict[str, Any],
) -> IdempotencyRecord | None:
    if not key:
        return None
    record = await db.scalar(
        select(IdempotencyRecord).where(
            IdempotencyRecord.organization_id == organization_id,
            IdempotencyRecord.idempotency_key == key,
            IdempotencyRecord.method == method,
            IdempotencyRecord.path == path,
        )
    )
    if record and record.request_hash != request_digest(payload):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Idempotency-Key was already used with a different payload",
        )
    return record


def store_idempotency(
    db: AsyncSession,
    organization_id: str,
    key: str | None,
    method: str,
    path: str,
    payload: dict[str, Any],
    resource_type: str,
    resource_id: str,
) -> None:
    if key:
        db.add(
            IdempotencyRecord(
                organization_id=organization_id,
                idempotency_key=key,
                method=method,
                path=path,
                request_hash=request_digest(payload),
                resource_type=resource_type,
                resource_id=resource_id,
            )
        )

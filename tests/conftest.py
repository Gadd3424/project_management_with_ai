import os
from collections.abc import AsyncIterator

os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///./test-project-ai.db"
os.environ["JWT_SECRET"] = "test-secret-that-is-at-least-thirty-two-characters"

import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from apps.api.app.db import Base, SessionLocal, engine
from apps.api.app.main import app
from apps.api.app.models import Organization, OrganizationMember, User
from apps.api.app.security import hash_password


@pytest_asyncio.fixture(autouse=True)
async def database() -> AsyncIterator[None]:
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
        await connection.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture
async def seeded() -> dict[str, str]:
    async with SessionLocal() as db:
        owner = User(email="owner@example.com", display_name="Owner", password_hash=hash_password("Password123!"))
        outsider = User(
            email="outsider@example.com", display_name="Outsider", password_hash=hash_password("Password123!")
        )
        db.add_all([owner, outsider])
        await db.flush()
        org = Organization(name="Test Org", slug="test-org", created_by=owner.id)
        other_org = Organization(name="Other Org", slug="other-org", created_by=outsider.id)
        db.add_all([org, other_org])
        await db.flush()
        db.add_all(
            [
                OrganizationMember(organization_id=org.id, user_id=owner.id, role="owner"),
                OrganizationMember(organization_id=other_org.id, user_id=outsider.id, role="owner"),
            ]
        )
        await db.commit()
        return {"owner_id": owner.id, "org_id": org.id, "other_org_id": other_org.id}


@pytest_asyncio.fixture
async def client() -> AsyncIterator[AsyncClient]:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as value:
        yield value


@pytest_asyncio.fixture
async def auth_headers(client: AsyncClient, seeded: dict[str, str]) -> dict[str, str]:
    response = await client.post("/api/v1/auth/login", json={"email": "owner@example.com", "password": "Password123!"})
    assert response.status_code == 200
    return {
        "Authorization": f"Bearer {response.json()['access_token']}",
        "X-Organization-ID": seeded["org_id"],
    }

import asyncio
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from apps.api.app.db import SessionLocal
from apps.api.app.models import Organization, OrganizationMember, Project, Task, User
from apps.api.app.security import hash_password


async def seed() -> None:
    async with SessionLocal() as db:
        existing = await db.scalar(select(User).where(User.email == "demo@example.com"))
        if existing:
            print("Demo data already exists")
            return
        user = User(
            email="demo@example.com",
            display_name="Demo Manager",
            password_hash=hash_password("DemoPass123!"),
        )
        db.add(user)
        await db.flush()
        organization = Organization(name="Demo Organization", slug="demo", created_by=user.id)
        db.add(organization)
        await db.flush()
        db.add(OrganizationMember(organization_id=organization.id, user_id=user.id, role="owner"))
        project = Project(
            organization_id=organization.id,
            name="AIプロジェクト管理MVP",
            description="意思決定支援AIを備えたカンバンのデモ",
            created_by=user.id,
        )
        db.add(project)
        await db.flush()
        tasks = [
            Task(
                organization_id=organization.id,
                project_id=project.id,
                title="認証フローを確認",
                description="CookieとCSRFの統合テストを完了する",
                status="in_progress",
                priority="high",
                assignee_id=user.id,
                due_at=datetime.now(UTC) + timedelta(days=2),
                created_by=user.id,
            ),
            Task(
                organization_id=organization.id,
                project_id=project.id,
                title="AI提案パネルをレビュー",
                description="根拠と確信度の表示を確認する",
                status="todo",
                priority="medium",
                due_at=datetime.now(UTC) + timedelta(days=5),
                created_by=user.id,
            ),
            Task(
                organization_id=organization.id,
                project_id=project.id,
                title="初期API設計",
                description="OpenAPI契約を確定済み",
                status="done",
                priority="medium",
                assignee_id=user.id,
                due_at=datetime.now(UTC) - timedelta(days=1),
                created_by=user.id,
            ),
        ]
        db.add_all(tasks)
        await db.commit()
        print(f"Seeded demo user and organization {organization.id}")


if __name__ == "__main__":
    asyncio.run(seed())

from httpx import AsyncClient

from apps.api.app.db import SessionLocal
from apps.api.app.models import OrganizationMember, User
from apps.api.app.security import hash_password


async def _add_user(org_id: str, email: str, role: str) -> str:
    async with SessionLocal() as db:
        user = User(email=email, display_name=email.split("@")[0], password_hash=hash_password("Password123!"))
        db.add(user)
        await db.flush()
        db.add(OrganizationMember(organization_id=org_id, user_id=user.id, role=role))
        await db.commit()
        return user.id


async def _login(client: AsyncClient, email: str, org_id: str) -> dict[str, str]:
    response = await client.post("/api/v1/auth/login", json={"email": email, "password": "Password123!"})
    return {"Authorization": f"Bearer {response.json()['access_token']}", "X-Organization-ID": org_id}


async def test_project_invitation_access_roles_and_chat(
    client: AsyncClient, auth_headers: dict[str, str], seeded: dict[str, str]
) -> None:
    editor_id = await _add_user(seeded["org_id"], "editor@example.com", "member")
    viewer_id = await _add_user(seeded["org_id"], "project-viewer@example.com", "viewer")
    project = (await client.post("/api/v1/projects", headers=auth_headers, json={"name": "共同プロジェクト"})).json()

    invited = await client.post(
        f"/api/v1/projects/{project['id']}/invitations",
        headers=auth_headers,
        json={"invitations": [
            {"user_id": editor_id, "role": "editor"},
            {"user_id": viewer_id, "role": "viewer"},
        ]},
    )
    assert invited.status_code == 201
    invitations = {item["user_id"]: item for item in invited.json()}

    editor_headers = await _login(client, "editor@example.com", seeded["org_id"])
    assert (await client.get(f"/api/v1/projects/{project['id']}", headers=editor_headers)).status_code == 404
    accepted = await client.post(
        f"/api/v1/project-invitations/{invitations[editor_id]['id']}/accept",
        headers=editor_headers,
        json={"version": invitations[editor_id]["version"]},
    )
    assert accepted.status_code == 204
    dashboard = await client.get("/api/v1/project-dashboard", headers=editor_headers)
    assert [item["id"] for item in dashboard.json()] == [project["id"]]
    assert dashboard.json()[0]["my_role"] == "editor"
    task = await client.post(
        f"/api/v1/projects/{project['id']}/tasks", headers=editor_headers, json={"title": "編集者タスク"}
    )
    assert task.status_code == 201

    message = await client.post(
        f"/api/v1/projects/{project['id']}/messages", headers=editor_headers, json={"body": "進捗を共有します"}
    )
    assert message.status_code == 201
    history = await client.get(f"/api/v1/projects/{project['id']}/messages", headers=auth_headers)
    assert history.status_code == 200
    assert history.json()["items"][0]["body"] == "進捗を共有します"

    viewer_headers = await _login(client, "project-viewer@example.com", seeded["org_id"])
    accepted = await client.post(
        f"/api/v1/project-invitations/{invitations[viewer_id]['id']}/accept",
        headers=viewer_headers,
        json={"version": invitations[viewer_id]["version"]},
    )
    assert accepted.status_code == 204
    assert (
        await client.post(
            f"/api/v1/projects/{project['id']}/tasks", headers=viewer_headers, json={"title": "拒否される"}
        )
    ).status_code == 403
    assert (
        await client.post(
            f"/api/v1/projects/{project['id']}/messages", headers=viewer_headers, json={"body": "確認しました"}
        )
    ).status_code == 201


async def test_member_cannot_invite_and_cross_tenant_user_is_rejected(
    client: AsyncClient, auth_headers: dict[str, str], seeded: dict[str, str]
) -> None:
    member_id = await _add_user(seeded["org_id"], "plain-member@example.com", "member")
    external_id = await _add_user(seeded["other_org_id"], "external@example.com", "viewer")
    project = (await client.post("/api/v1/projects", headers=auth_headers, json={"name": "権限テスト"})).json()
    invited = (await client.post(
        f"/api/v1/projects/{project['id']}/invitations",
        headers=auth_headers,
        json={"invitations": [{"user_id": member_id, "role": "editor"}]},
    )).json()[0]
    member_headers = await _login(client, "plain-member@example.com", seeded["org_id"])
    await client.post(
        f"/api/v1/project-invitations/{invited['id']}/accept",
        headers=member_headers,
        json={"version": invited["version"]},
    )
    denied = await client.post(
        f"/api/v1/projects/{project['id']}/invitations",
        headers=member_headers,
        json={"invitations": [{"user_id": seeded["owner_id"], "role": "editor"}]},
    )
    assert denied.status_code == 403
    cross_tenant = await client.post(
        f"/api/v1/projects/{project['id']}/invitations",
        headers=auth_headers,
        json={"invitations": [{"user_id": external_id, "role": "viewer"}]},
    )
    assert cross_tenant.status_code == 422

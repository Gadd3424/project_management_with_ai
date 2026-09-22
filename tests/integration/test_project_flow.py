from httpx import AsyncClient

from apps.api.app.db import SessionLocal
from apps.api.app.models import OrganizationMember, User
from apps.api.app.security import hash_password


async def test_project_task_suggestion_feedback_flow(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    project_response = await client.post(
        "/api/v1/projects",
        headers=auth_headers,
        json={"name": "MVP", "description": "Vertical slice"},
    )
    assert project_response.status_code == 201
    project = project_response.json()

    task_response = await client.post(
        f"/api/v1/projects/{project['id']}/tasks",
        headers=auth_headers,
        json={"title": "Review release", "description": "Confirm release checklist", "priority": "high"},
    )
    assert task_response.status_code == 201
    task = task_response.json()

    generated = await client.post(f"/api/v1/tasks/{task['id']}/suggestions/generate", headers=auth_headers)
    assert generated.status_code == 201
    suggestions = generated.json()
    assert {item["suggestion_type"] for item in suggestions} == {"delay_risk", "next_action"}
    assert all(0 <= item["confidence"] <= 1 for item in suggestions)
    assert all(item["rationale"] for item in suggestions)

    next_action = next(item for item in suggestions if item["suggestion_type"] == "next_action")
    accepted = await client.post(f"/api/v1/suggestions/{next_action['id']}/accept", headers=auth_headers, json={})
    assert accepted.status_code == 200
    assert accepted.json()["decision"] == "accepted"

    diff = await client.get(f"/api/v1/suggestions/{next_action['id']}/diff", headers=auth_headers)
    assert diff.status_code == 200
    assert diff.json()["before"] != diff.json()["after"]

    applied = await client.post(f"/api/v1/suggestions/{next_action['id']}/apply", headers=auth_headers)
    assert applied.status_code == 200
    assert "次のアクション" in applied.json()["description"]

    feedback = await client.post(
        f"/api/v1/suggestions/{next_action['id']}/feedback",
        headers=auth_headers,
        json={"rating": 4, "comment": "Useful"},
    )
    assert feedback.status_code == 201

    audit = await client.get("/api/v1/audit-logs", headers=auth_headers)
    assert audit.status_code == 200
    actions = {item["action"] for item in audit.json()}
    assert {"project.create", "task.create", "suggestion.accepted", "suggestion.apply"} <= actions


async def test_optimistic_lock_rejects_stale_task(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    project = (await client.post("/api/v1/projects", headers=auth_headers, json={"name": "Lock test"})).json()
    task = (
        await client.post(f"/api/v1/projects/{project['id']}/tasks", headers=auth_headers, json={"title": "Concurrent"})
    ).json()
    first = await client.patch(
        f"/api/v1/tasks/{task['id']}", headers=auth_headers, json={"status": "in_progress", "version": 1}
    )
    assert first.status_code == 200
    stale = await client.patch(
        f"/api/v1/tasks/{task['id']}", headers=auth_headers, json={"status": "done", "version": 1}
    )
    assert stale.status_code == 409


async def test_project_creation_is_idempotent(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    headers = {**auth_headers, "Idempotency-Key": "create-project-001"}
    first = await client.post("/api/v1/projects", headers=headers, json={"name": "Only once"})
    replay = await client.post("/api/v1/projects", headers=headers, json={"name": "Only once"})
    assert first.status_code == 201
    assert replay.status_code == 201
    assert first.json()["id"] == replay.json()["id"]

    conflict = await client.post("/api/v1/projects", headers=headers, json={"name": "Different"})
    assert conflict.status_code == 409


async def test_project_crud_and_ai_proposals(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    defaults = await client.post(
        "/api/v1/projects/ai/defaults",
        headers=auth_headers,
        json={"name": "AI導入プロジェクト"},
    )
    assert defaults.status_code == 201
    proposal = defaults.json()
    assert proposal["suggestion_type"] == "project_defaults"
    assert proposal["proposed_values"]["objective"]
    assert proposal["provider"] == "mock"

    created = await client.post(
        "/api/v1/projects",
        headers=auth_headers,
        json={
            "name": "AI導入プロジェクト",
            "description": proposal["proposed_values"]["description"],
            "objective": proposal["proposed_values"]["objective"],
            "success_criteria": proposal["proposed_values"]["success_criteria"],
            "ai_suggestion_id": proposal["id"],
        },
    )
    assert created.status_code == 201
    project = created.json()
    assert project["objective"] == proposal["proposed_values"]["objective"]

    task = await client.post(
        f"/api/v1/projects/{project['id']}/tasks",
        headers=auth_headers,
        json={"title": "完了済み", "status": "done"},
    )
    assert task.status_code == 201
    assert task.json()["status"] == "todo"
    task = await client.patch(
        f"/api/v1/tasks/{task.json()['id']}",
        headers=auth_headers,
        json={"status": "done", "version": task.json()["version"]},
    )
    assert task.status_code == 200
    change = await client.post(
        f"/api/v1/projects/{project['id']}/ai/change-proposal",
        headers=auth_headers,
        json={},
    )
    assert change.status_code == 201
    assert change.json()["proposed_values"]["status"] == "archived"

    updated = await client.patch(
        f"/api/v1/projects/{project['id']}",
        headers=auth_headers,
        json={"status": "archived", "version": project["version"], "ai_suggestion_id": change.json()["id"]},
    )
    assert updated.status_code == 200
    assert updated.json()["status"] == "archived"

    removed = await client.request(
        "DELETE",
        f"/api/v1/projects/{project['id']}",
        headers=auth_headers,
        json={"version": updated.json()["version"]},
    )
    assert removed.status_code == 204
    assert (await client.get("/api/v1/projects", headers=auth_headers)).json() == []
    assert (await client.get(f"/api/v1/tasks/{task.json()['id']}", headers=auth_headers)).status_code == 404


async def test_viewer_cannot_manage_projects(
    client: AsyncClient, auth_headers: dict[str, str], seeded: dict[str, str]
) -> None:
    async with SessionLocal() as db:
        viewer = User(
            email="viewer@example.com",
            display_name="Viewer",
            password_hash=hash_password("Password123!"),
        )
        db.add(viewer)
        await db.flush()
        db.add(OrganizationMember(organization_id=seeded["org_id"], user_id=viewer.id, role="viewer"))
        await db.commit()
    login = await client.post("/api/v1/auth/login", json={"email": "viewer@example.com", "password": "Password123!"})
    viewer_headers = {
        "Authorization": f"Bearer {login.json()['access_token']}",
        "X-Organization-ID": seeded["org_id"],
    }
    denied = await client.post("/api/v1/projects", headers=viewer_headers, json={"name": "Denied"})
    assert denied.status_code == 403
    ai_denied = await client.post(
        "/api/v1/projects/ai/defaults", headers=viewer_headers, json={"name": "Denied"}
    )
    assert ai_denied.status_code == 403


async def test_initial_ai_and_manual_tasks_are_created_atomically(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    suggested = await client.post(
        "/api/v1/projects/ai/task-suggestions",
        headers=auth_headers,
        json={
            "name": "新サービス",
            "description": "顧客向けサービスを立ち上げる",
            "objective": "顧客価値を検証する",
            "success_criteria": "最初の顧客が利用を完了する",
        },
    )
    assert suggested.status_code == 201
    proposal = suggested.json()
    assert proposal["suggestion_type"] == "project_initial_tasks"
    assert len(proposal["proposed_values"]["tasks"]) >= 3

    selected = proposal["proposed_values"]["tasks"][0]
    created = await client.post(
        "/api/v1/projects",
        headers={**auth_headers, "Idempotency-Key": "project-with-tasks"},
        json={
            "name": "新サービス",
            "objective": "顧客価値を検証する",
            "success_criteria": "最初の顧客が利用を完了する",
            "ai_task_suggestion_id": proposal["id"],
            "initial_tasks": [
                {
                    "title": selected["title"],
                    "description": selected["description"],
                    "notes": selected["notes"],
                    "priority": selected["priority"],
                },
                {"title": "手動で追加", "notes": "利用者が追記", "priority": "urgent"},
            ],
        },
    )
    assert created.status_code == 201
    project = created.json()
    replay = await client.post(
        "/api/v1/projects",
        headers={**auth_headers, "Idempotency-Key": "project-with-tasks"},
        json={
            "name": "新サービス",
            "objective": "顧客価値を検証する",
            "success_criteria": "最初の顧客が利用を完了する",
            "ai_task_suggestion_id": proposal["id"],
            "initial_tasks": [
                {
                    "title": selected["title"], "description": selected["description"],
                    "notes": selected["notes"], "priority": selected["priority"],
                },
                {"title": "手動で追加", "notes": "利用者が追記", "priority": "urgent"},
            ],
        },
    )
    assert replay.status_code == 201
    tasks = (await client.get(f"/api/v1/projects/{project['id']}/tasks", headers=auth_headers)).json()
    assert len(tasks) == 2
    assert {task["title"] for task in tasks} == {selected["title"], "手動で追加"}
    assert all(task["status"] == "todo" for task in tasks)


async def test_task_reorder_and_soft_delete(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    project = (await client.post("/api/v1/projects", headers=auth_headers, json={"name": "Kanban"})).json()
    first = (await client.post(
        f"/api/v1/projects/{project['id']}/tasks", headers=auth_headers,
        json={"title": "First", "description": "概要", "notes": "補足"},
    )).json()
    second = (await client.post(
        f"/api/v1/projects/{project['id']}/tasks", headers=auth_headers, json={"title": "Second"},
    )).json()
    moved = await client.patch(
        f"/api/v1/projects/{project['id']}/tasks/reorder",
        headers=auth_headers,
        json={"tasks": [
            {"id": first["id"], "status": "in_progress", "position": 0, "version": first["version"]},
            {"id": second["id"], "status": "on_hold", "position": 0, "version": second["version"]},
        ]},
    )
    assert moved.status_code == 200
    by_id = {task["id"]: task for task in moved.json()}
    assert by_id[first["id"]]["status"] == "in_progress"
    assert by_id[second["id"]]["status"] == "on_hold"
    assert by_id[first["id"]]["notes"] == "補足"

    removed = await client.request(
        "DELETE", f"/api/v1/tasks/{first['id']}", headers=auth_headers,
        json={"version": by_id[first["id"]]["version"]},
    )
    assert removed.status_code == 204
    assert (await client.get(f"/api/v1/tasks/{first['id']}", headers=auth_headers)).status_code == 404

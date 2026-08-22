from httpx import AsyncClient


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

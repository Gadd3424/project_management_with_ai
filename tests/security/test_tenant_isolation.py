from httpx import AsyncClient


async def test_user_cannot_select_unrelated_organization(
    client: AsyncClient, auth_headers: dict[str, str], seeded: dict[str, str]
) -> None:
    attack_headers = {**auth_headers, "X-Organization-ID": seeded["other_org_id"]}
    response = await client.get("/api/v1/projects", headers=attack_headers)
    assert response.status_code == 403


async def test_resource_id_does_not_bypass_tenant_filter(
    client: AsyncClient, auth_headers: dict[str, str], seeded: dict[str, str]
) -> None:
    created = await client.post("/api/v1/projects", headers=auth_headers, json={"name": "Private"})
    assert created.status_code == 201
    attack_headers = {**auth_headers, "X-Organization-ID": seeded["other_org_id"]}
    response = await client.get(f"/api/v1/projects/{created.json()['id']}", headers=attack_headers)
    assert response.status_code == 403

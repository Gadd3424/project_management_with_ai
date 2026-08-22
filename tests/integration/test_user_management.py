from httpx import AsyncClient
from sqlalchemy import select

from apps.api.app.db import SessionLocal
from apps.api.app.domain.roles import MembershipStatus, OrganizationRole
from apps.api.app.models import (
    AuditLog,
    Comment,
    Organization,
    OrganizationMember,
    OutboxEvent,
    Project,
    Task,
    User,
    UserInvitation,
)
from apps.api.app.security import hash_password


async def add_member(organization_id: str, email: str, role: str) -> tuple[str, int]:
    async with SessionLocal() as db:
        user = User(email=email, display_name=email.split("@")[0], password_hash=hash_password("Password123!"))
        db.add(user)
        await db.flush()
        member = OrganizationMember(organization_id=organization_id, user_id=user.id, role=role)
        db.add(member)
        await db.commit()
        return user.id, member.version


async def login(client: AsyncClient, email: str) -> dict[str, str]:
    response = await client.post("/api/v1/auth/login", json={"email": email, "password": "Password123!"})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


async def test_owner_can_invite_accept_and_list_user(
    client: AsyncClient, auth_headers: dict[str, str], seeded: dict[str, str]
) -> None:
    invited = await client.post(
        f"/api/v1/organizations/{seeded['org_id']}/users/invitations",
        headers=auth_headers,
        json={"email": "New.User@example.com", "display_name": "New User", "role": "member"},
    )
    assert invited.status_code == 201, invited.text
    token = invited.json()["development_token"]
    assert token

    accepted = await client.post(
        "/api/v1/auth/invitations/accept",
        json={"token": token, "display_name": "New User", "password": "NewPassword123!"},
    )
    assert accepted.status_code == 201, accepted.text

    users = await client.get(
        f"/api/v1/organizations/{seeded['org_id']}/users?search=new.user",
        headers=auth_headers,
    )
    assert users.status_code == 200
    assert users.json()["total"] == 1
    assert users.json()["items"][0]["email"] == "new.user@example.com"


async def test_cross_organization_user_list_is_denied(
    client: AsyncClient, auth_headers: dict[str, str], seeded: dict[str, str]
) -> None:
    response = await client.get(
        f"/api/v1/organizations/{seeded['other_org_id']}/users",
        headers=auth_headers,
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "CROSS_ORGANIZATION_ACCESS_DENIED"


async def test_last_owner_cannot_be_suspended_deleted_or_demoted(
    client: AsyncClient, auth_headers: dict[str, str], seeded: dict[str, str]
) -> None:
    response = await client.post(
        f"/api/v1/organizations/{seeded['org_id']}/users/{seeded['owner_id']}/suspend",
        headers=auth_headers,
        json={"reason": "security test", "version": 1},
    )
    assert response.status_code == 403
    deleted = await client.post(
        f"/api/v1/organizations/{seeded['org_id']}/users/{seeded['owner_id']}/delete",
        headers=auth_headers,
        json={"reason": "must retain owner", "version": 1},
    )
    assert deleted.status_code == 403
    demoted = await client.patch(
        f"/api/v1/organizations/{seeded['org_id']}/users/{seeded['owner_id']}/role",
        headers=auth_headers,
        json={"role": "member", "reason": "must retain owner", "version": 1},
    )
    assert demoted.status_code == 409
    assert demoted.json()["error"]["code"] == "LAST_OWNER_CANNOT_BE_REMOVED"


async def test_stale_role_change_is_rejected(
    client: AsyncClient, auth_headers: dict[str, str], seeded: dict[str, str]
) -> None:
    invited = await client.post(
        f"/api/v1/organizations/{seeded['org_id']}/users/invitations",
        headers=auth_headers,
        json={"email": "role@example.com", "display_name": "Role User", "role": "member"},
    )
    token = invited.json()["development_token"]
    accepted = await client.post(
        "/api/v1/auth/invitations/accept",
        json={"token": token, "display_name": "Role User", "password": "NewPassword123!"},
    )
    user_id = accepted.json()["user_id"]
    changed = await client.patch(
        f"/api/v1/organizations/{seeded['org_id']}/users/{user_id}/role",
        headers=auth_headers,
        json={"role": "viewer", "version": 1, "reason": "read only assignment"},
    )
    assert changed.status_code == 200
    stale = await client.patch(
        f"/api/v1/organizations/{seeded['org_id']}/users/{user_id}/role",
        headers=auth_headers,
        json={"role": "member", "version": 1, "reason": "stale update check"},
    )
    assert stale.status_code == 409
    assert stale.json()["error"]["code"] == "VERSION_CONFLICT"


async def test_admin_can_manage_member_but_cannot_modify_owner(
    client: AsyncClient, auth_headers: dict[str, str], seeded: dict[str, str]
) -> None:
    admin_id, _ = await add_member(seeded["org_id"], "admin@example.com", "admin")
    member_id, member_version = await add_member(seeded["org_id"], "member@example.com", "member")
    admin_headers = await login(client, "admin@example.com")

    invited = await client.post(
        f"/api/v1/organizations/{seeded['org_id']}/users/invitations",
        headers=admin_headers,
        json={"email": "invited-member@example.com", "display_name": "Invited", "role": "member"},
    )
    assert invited.status_code == 201
    delete_member = await client.post(
        f"/api/v1/organizations/{seeded['org_id']}/users/{member_id}/delete",
        headers=admin_headers,
        json={"reason": "member left organization", "version": member_version},
    )
    assert delete_member.status_code == 204
    delete_owner = await client.post(
        f"/api/v1/organizations/{seeded['org_id']}/users/{seeded['owner_id']}/delete",
        headers=admin_headers,
        json={"reason": "forbidden owner operation", "version": 1},
    )
    assert delete_owner.status_code == 403
    demote_owner = await client.patch(
        f"/api/v1/organizations/{seeded['org_id']}/users/{seeded['owner_id']}/role",
        headers=admin_headers,
        json={"role": "member", "reason": "forbidden owner demotion", "version": 1},
    )
    assert demote_owner.status_code == 403
    assert admin_id


async def test_admin_cannot_self_promote_or_delete_user_in_another_organization(
    client: AsyncClient, seeded: dict[str, str]
) -> None:
    admin_id, admin_version = await add_member(seeded["org_id"], "bounded-admin@example.com", "admin")
    foreign_id, foreign_version = await add_member(seeded["other_org_id"], "foreign-member@example.com", "member")
    headers = await login(client, "bounded-admin@example.com")
    promote_self = await client.patch(
        f"/api/v1/organizations/{seeded['org_id']}/users/{admin_id}/role",
        headers=headers,
        json={"role": "owner", "reason": "forbidden self promotion", "version": admin_version},
    )
    assert promote_self.status_code == 403
    foreign_delete = await client.post(
        f"/api/v1/organizations/{seeded['org_id']}/users/{foreign_id}/delete",
        headers=headers,
        json={"reason": "cross tenant attempt", "version": foreign_version},
    )
    assert foreign_delete.status_code == 404


async def test_member_and_viewer_cannot_access_management_api(client: AsyncClient, seeded: dict[str, str]) -> None:
    await add_member(seeded["org_id"], "member-denied@example.com", "member")
    await add_member(seeded["org_id"], "viewer-denied@example.com", "viewer")
    for email in ("member-denied@example.com", "viewer-denied@example.com"):
        headers = await login(client, email)
        response = await client.get(f"/api/v1/organizations/{seeded['org_id']}/users", headers=headers)
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "FORBIDDEN"


async def test_invitation_is_single_use_and_duplicate_and_revoked_are_rejected(
    client: AsyncClient, auth_headers: dict[str, str], seeded: dict[str, str]
) -> None:
    path = f"/api/v1/organizations/{seeded['org_id']}/users/invitations"
    payload = {"email": "single-use@example.com", "display_name": "Single Use", "role": "member"}
    invited = await client.post(path, headers=auth_headers, json=payload)
    assert invited.status_code == 201
    duplicate = await client.post(path, headers=auth_headers, json=payload)
    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["code"] == "INVITATION_ALREADY_EXISTS"
    token = invited.json()["development_token"]
    accepted_payload = {"token": token, "display_name": "Single Use", "password": "NewPassword123!"}
    assert (await client.post("/api/v1/auth/invitations/accept", json=accepted_payload)).status_code == 201
    reused = await client.post("/api/v1/auth/invitations/accept", json=accepted_payload)
    assert reused.status_code == 409

    revoked = await client.post(
        path,
        headers=auth_headers,
        json={"email": "revoked@example.com", "display_name": "Revoked", "role": "member"},
    )
    revoke_path = f"{path}/{revoked.json()['id']}/revoke"
    assert (await client.post(revoke_path, headers=auth_headers)).status_code == 204
    rejected = await client.post(
        "/api/v1/auth/invitations/accept",
        json={"token": revoked.json()["development_token"], "display_name": "Revoked", "password": "Password123!"},
    )
    assert rejected.status_code == 409
    assert rejected.json()["error"]["code"] == "INVITATION_REVOKED"


async def test_expired_invitation_is_rejected(
    client: AsyncClient, auth_headers: dict[str, str], seeded: dict[str, str]
) -> None:
    invited = await client.post(
        f"/api/v1/organizations/{seeded['org_id']}/users/invitations",
        headers=auth_headers,
        json={"email": "expired@example.com", "display_name": "Expired", "role": "member"},
    )
    async with SessionLocal() as db:
        invitation = await db.get(UserInvitation, invited.json()["id"])
        invitation.expires_at = invitation.created_at
        await db.commit()
    response = await client.post(
        "/api/v1/auth/invitations/accept",
        json={"token": invited.json()["development_token"], "display_name": "Expired", "password": "Password123!"},
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "INVITATION_EXPIRED"


async def test_delete_invalidates_session_preserves_history_and_restore_is_scoped(
    client: AsyncClient, auth_headers: dict[str, str], seeded: dict[str, str]
) -> None:
    user_id, version = await add_member(seeded["org_id"], "history@example.com", "member")
    async with SessionLocal() as db:
        other_membership = OrganizationMember(organization_id=seeded["other_org_id"], user_id=user_id, role="member")
        project = Project(organization_id=seeded["org_id"], name="History", created_by=seeded["owner_id"])
        db.add_all([other_membership, project])
        await db.flush()
        task = Task(organization_id=seeded["org_id"], project_id=project.id, title="Keep", created_by=user_id)
        db.add(task)
        await db.flush()
        db.add(Comment(organization_id=seeded["org_id"], task_id=task.id, body="Keep", created_by=user_id))
        await db.commit()
        task_id = task.id
    member_headers = await login(client, "history@example.com")
    deleted = await client.post(
        f"/api/v1/organizations/{seeded['org_id']}/users/{user_id}/delete",
        headers=auth_headers,
        json={"reason": "departure", "version": version},
    )
    assert deleted.status_code == 204
    assert (await client.get("/api/v1/auth/me", headers=member_headers)).status_code == 401
    async with SessionLocal() as db:
        own = await db.scalar(
            select(OrganizationMember).where(
                OrganizationMember.organization_id == seeded["org_id"], OrganizationMember.user_id == user_id
            )
        )
        other = await db.scalar(
            select(OrganizationMember).where(
                OrganizationMember.organization_id == seeded["other_org_id"], OrganizationMember.user_id == user_id
            )
        )
        assert own.status == MembershipStatus.DELETED
        assert other.status == MembershipStatus.ACTIVE
        assert await db.get(Task, task_id)
        assert await db.scalar(select(Comment).where(Comment.task_id == task_id))
    restored = await client.post(
        f"/api/v1/organizations/{seeded['org_id']}/users/{user_id}/restore",
        headers=auth_headers,
        json={"reason": "return", "version": version + 1},
    )
    assert restored.status_code == 200
    assert restored.json()["status"] == "active"


async def test_owner_can_grant_and_revoke_admin_and_token_is_invalidated(
    client: AsyncClient, auth_headers: dict[str, str], seeded: dict[str, str]
) -> None:
    user_id, version = await add_member(seeded["org_id"], "promoted@example.com", "member")
    old_headers = await login(client, "promoted@example.com")
    promoted = await client.patch(
        f"/api/v1/organizations/{seeded['org_id']}/users/{user_id}/role",
        headers=auth_headers,
        json={"role": "admin", "reason": "project administrator", "version": version},
    )
    assert promoted.status_code == 200
    assert promoted.json()["role"] == "admin"
    assert (await client.get("/api/v1/auth/me", headers=old_headers)).status_code == 401
    demoted = await client.patch(
        f"/api/v1/organizations/{seeded['org_id']}/users/{user_id}/role",
        headers=auth_headers,
        json={"role": "member", "reason": "assignment completed", "version": version + 1},
    )
    assert demoted.status_code == 200
    assert demoted.json()["role"] == "member"


async def test_audit_records_changes_reasons_and_denials_without_secrets(
    client: AsyncClient, auth_headers: dict[str, str], seeded: dict[str, str]
) -> None:
    member_id, version = await add_member(seeded["org_id"], "audit@example.com", "member")
    member_headers = await login(client, "audit@example.com")
    denied = await client.get(f"/api/v1/organizations/{seeded['org_id']}/users", headers=member_headers)
    assert denied.status_code == 403
    changed = await client.patch(
        f"/api/v1/organizations/{seeded['org_id']}/users/{member_id}/role",
        headers=auth_headers,
        json={"role": "viewer", "reason": "audit role reason", "version": version},
    )
    assert changed.status_code == 200
    deleted = await client.post(
        f"/api/v1/organizations/{seeded['org_id']}/users/{member_id}/delete",
        headers=auth_headers,
        json={"reason": "audit delete reason", "version": version + 1},
    )
    assert deleted.status_code == 204
    async with SessionLocal() as db:
        logs = (await db.scalars(select(AuditLog).where(AuditLog.organization_id == seeded["org_id"]))).all()
        actions = {log.action for log in logs}
        assert {"user.admin.access_denied", "user.role.change", "user.delete"} <= actions
        role_log = next(log for log in logs if log.action == "user.role.change")
        assert role_log.previous_values["role"] == OrganizationRole.MEMBER.value
        assert role_log.new_values["role"] == OrganizationRole.VIEWER.value
        assert role_log.reason == "audit role reason"
        serialized = str([log.details | log.previous_values | log.new_values for log in logs]).lower()
        assert "password" not in serialized
        assert "token" not in serialized


async def test_direct_registration_requires_setting_and_forces_password_change(
    client: AsyncClient, auth_headers: dict[str, str], seeded: dict[str, str]
) -> None:
    path = f"/api/v1/organizations/{seeded['org_id']}/users/direct"
    payload = {"email": "direct@example.com", "display_name": "Direct", "role": "member"}
    disabled = await client.post(path, headers=auth_headers, json=payload)
    assert disabled.status_code == 403
    assert disabled.json()["error"]["code"] == "DIRECT_USER_CREATION_DISABLED"
    async with SessionLocal() as db:
        organization = await db.get(Organization, seeded["org_id"])
        organization.allow_direct_user_creation = True
        await db.commit()
    created = await client.post(path, headers=auth_headers, json=payload)
    assert created.status_code == 201, created.text
    temporary_password = created.json()["temporary_password"]
    assert temporary_password
    async with SessionLocal() as db:
        event = await db.scalar(select(OutboxEvent).where(OutboxEvent.event_type == "user.direct_registration.created"))
        assert "password" not in str(event.payload).lower()
    logged_in = await client.post(
        "/api/v1/auth/login", json={"email": payload["email"], "password": temporary_password}
    )
    assert logged_in.status_code == 200
    token = logged_in.json()["access_token"]
    assert logged_in.json()["user"]["force_password_change"] is True
    headers = {"Authorization": f"Bearer {token}"}
    assert (await client.get("/api/v1/organizations", headers=headers)).status_code == 403
    changed = await client.post(
        "/api/v1/auth/change-password",
        headers=headers,
        json={"current_password": temporary_password, "new_password": "ChangedPassword123!"},
    )
    assert changed.status_code == 204
    assert (await client.get("/api/v1/auth/me", headers=headers)).status_code == 401
    relogin = await client.post(
        "/api/v1/auth/login",
        json={"email": payload["email"], "password": "ChangedPassword123!"},
    )
    assert relogin.status_code == 200
    assert relogin.json()["user"]["force_password_change"] is False

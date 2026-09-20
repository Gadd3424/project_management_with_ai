from enum import StrEnum

from .roles import OrganizationRole


class OrganizationPermission(StrEnum):
    PROJECTS_CREATE = "projects.create"
    PROJECTS_UPDATE = "projects.update"
    PROJECTS_DELETE = "projects.delete"
    PROJECTS_AI_SUGGEST = "projects.ai_suggest"
    USERS_READ = "organization.users.read"
    USERS_CREATE = "organization.users.create"
    USERS_UPDATE = "organization.users.update"
    USERS_DEACTIVATE = "organization.users.deactivate"
    USERS_DELETE = "organization.users.delete"
    USERS_RESTORE = "organization.users.restore"
    USERS_PURGE = "organization.users.purge"
    USERS_CHANGE_ROLE = "organization.users.change_role"
    USERS_GRANT_ADMIN = "organization.users.grant_admin"
    USERS_REVOKE_ADMIN = "organization.users.revoke_admin"
    USERS_RESET_PASSWORD = "organization.users.reset_password"
    USERS_RESEND_INVITATION = "organization.users.resend_invitation"
    AUDIT_LOGS_READ = "organization.audit_logs.read"
    SETTINGS_UPDATE = "organization.settings.update"
    OWNERSHIP_TRANSFER = "organization.ownership.transfer"


OWNER_PERMISSIONS = frozenset(OrganizationPermission)
ADMIN_PERMISSIONS = frozenset(
    {
        OrganizationPermission.PROJECTS_CREATE,
        OrganizationPermission.PROJECTS_UPDATE,
        OrganizationPermission.PROJECTS_DELETE,
        OrganizationPermission.PROJECTS_AI_SUGGEST,
        OrganizationPermission.USERS_READ,
        OrganizationPermission.USERS_CREATE,
        OrganizationPermission.USERS_UPDATE,
        OrganizationPermission.USERS_DEACTIVATE,
        OrganizationPermission.USERS_DELETE,
        OrganizationPermission.USERS_RESTORE,
        OrganizationPermission.USERS_CHANGE_ROLE,
        OrganizationPermission.USERS_REVOKE_ADMIN,
        OrganizationPermission.USERS_RESET_PASSWORD,
        OrganizationPermission.USERS_RESEND_INVITATION,
        OrganizationPermission.AUDIT_LOGS_READ,
    }
)
ROLE_PERMISSIONS: dict[OrganizationRole, frozenset[OrganizationPermission]] = {
    OrganizationRole.OWNER: OWNER_PERMISSIONS,
    OrganizationRole.ADMIN: ADMIN_PERMISSIONS,
    OrganizationRole.MEMBER: frozenset(
        {
            OrganizationPermission.PROJECTS_CREATE,
            OrganizationPermission.PROJECTS_UPDATE,
            OrganizationPermission.PROJECTS_DELETE,
            OrganizationPermission.PROJECTS_AI_SUGGEST,
        }
    ),
    OrganizationRole.VIEWER: frozenset(),
}


def permissions_for_role(role: OrganizationRole | str) -> frozenset[OrganizationPermission]:
    normalized = role if isinstance(role, OrganizationRole) else OrganizationRole(role)
    return ROLE_PERMISSIONS[normalized]


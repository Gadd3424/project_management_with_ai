"""Organization-scoped RBAC and user lifecycle management.

This migration is intentionally schema-aware because 0001 creates current metadata
for new installations. Existing installations only receive the missing objects.
"""

import uuid
from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op

from apps.api.app.models import OutboxEvent, UserInvitation

revision = "0002_user_management"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def _columns(table: str) -> set[str]:
    return {column["name"] for column in sa.inspect(op.get_bind()).get_columns(table)}


def _add(table: str, column: sa.Column) -> None:
    if column.name not in _columns(table):
        op.add_column(table, column)


def upgrade() -> None:
    _add("users", sa.Column("status", sa.String(20), nullable=False, server_default="active"))
    _add("users", sa.Column("is_email_verified", sa.Boolean(), nullable=False, server_default=sa.false()))
    _add("users", sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True))
    _add("users", sa.Column("password_changed_at", sa.DateTime(timezone=True), nullable=True))
    _add("users", sa.Column("failed_login_count", sa.Integer(), nullable=False, server_default="0"))
    _add("users", sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True))
    _add("users", sa.Column("auth_version", sa.Integer(), nullable=False, server_default="1"))
    _add("users", sa.Column("force_password_change", sa.Boolean(), nullable=False, server_default=sa.false()))

    _add(
        "organizations", sa.Column("allow_admin_manage_admins", sa.Boolean(), nullable=False, server_default=sa.false())
    )
    _add(
        "organizations",
        sa.Column("allow_direct_user_creation", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    _add("organizations", sa.Column("invitation_expiry_hours", sa.Integer(), nullable=False, server_default="72"))

    _add("organization_members", sa.Column("status", sa.String(20), nullable=False, server_default="active"))
    _add("organization_members", sa.Column("invited_by", sa.String(36), nullable=True))
    _add("organization_members", sa.Column("invited_at", sa.DateTime(timezone=True), nullable=True))
    _add("organization_members", sa.Column("joined_at", sa.DateTime(timezone=True), nullable=True))
    _add("organization_members", sa.Column("suspended_at", sa.DateTime(timezone=True), nullable=True))
    _add("organization_members", sa.Column("suspended_by", sa.String(36), nullable=True))
    _add("organization_members", sa.Column("deleted_by", sa.String(36), nullable=True))

    _add("audit_logs", sa.Column("target_user_id", sa.String(36), nullable=True))
    _add("audit_logs", sa.Column("previous_values", sa.JSON(), nullable=False, server_default="{}"))
    _add("audit_logs", sa.Column("new_values", sa.JSON(), nullable=False, server_default="{}"))
    _add("audit_logs", sa.Column("reason", sa.Text(), nullable=True))
    _add("audit_logs", sa.Column("result", sa.String(20), nullable=False, server_default="success"))
    _add("audit_logs", sa.Column("ip_address", sa.String(64), nullable=True))
    _add("audit_logs", sa.Column("user_agent", sa.String(500), nullable=True))

    UserInvitation.__table__.create(op.get_bind(), checkfirst=True)
    OutboxEvent.__table__.create(op.get_bind(), checkfirst=True)

    op.execute("UPDATE organization_members SET role = 'member' WHERE role NOT IN ('owner', 'admin')")
    op.execute(
        "UPDATE organization_members SET role = 'owner' WHERE user_id IN "
        "(SELECT created_by FROM organizations) AND role != 'owner'"
    )
    bind = op.get_bind()
    missing_creators = bind.execute(
        sa.text(
            "SELECT o.id, o.created_by FROM organizations o "
            "WHERE NOT EXISTS (SELECT 1 FROM organization_members m "
            "WHERE m.organization_id = o.id AND m.user_id = o.created_by)"
        )
    ).all()
    now = datetime.now(UTC)
    for organization_id, creator_id in missing_creators:
        bind.execute(
            sa.text(
                "INSERT INTO organization_members "
                "(id, organization_id, user_id, role, status, joined_at, created_at, updated_at, version) "
                "VALUES (:id, :organization_id, :user_id, 'owner', 'active', :now, :now, :now, 1)"
            ),
            {"id": str(uuid.uuid4()), "organization_id": organization_id, "user_id": creator_id, "now": now},
        )

    ownerless = bind.execute(
        sa.text(
            "SELECT o.id FROM organizations o WHERE NOT EXISTS "
            "(SELECT 1 FROM organization_members m WHERE m.organization_id = o.id "
            "AND m.role = 'owner' AND m.status = 'active' AND m.deleted_at IS NULL)"
        )
    ).all()
    if ownerless:
        raise RuntimeError(f"Ownerless organizations detected: {[row[0] for row in ownerless]}")

    inspector = sa.inspect(bind)
    index_names = {index["name"] for index in inspector.get_indexes("audit_logs")}
    if "ix_audit_logs_target_user_id" not in index_names:
        op.create_index("ix_audit_logs_target_user_id", "audit_logs", ["target_user_id"])
    if bind.dialect.name != "sqlite":
        existing_fk_columns = {
            tuple(fk["constrained_columns"]) for fk in inspector.get_foreign_keys("organization_members")
        }
        for column in ("invited_by", "suspended_by", "deleted_by"):
            name = f"fk_organization_members_{column}_users"
            if (column,) not in existing_fk_columns:
                op.create_foreign_key(name, "organization_members", "users", [column], ["id"])


def downgrade() -> None:
    OutboxEvent.__table__.drop(op.get_bind(), checkfirst=True)
    UserInvitation.__table__.drop(op.get_bind(), checkfirst=True)
    for table, names in {
        "audit_logs": [
            "user_agent",
            "ip_address",
            "result",
            "reason",
            "new_values",
            "previous_values",
            "target_user_id",
        ],
        "organization_members": [
            "deleted_by",
            "suspended_by",
            "suspended_at",
            "joined_at",
            "invited_at",
            "invited_by",
            "status",
        ],
        "organizations": ["invitation_expiry_hours", "allow_direct_user_creation", "allow_admin_manage_admins"],
        "users": [
            "force_password_change",
            "auth_version",
            "locked_until",
            "failed_login_count",
            "password_changed_at",
            "last_login_at",
            "is_email_verified",
            "status",
        ],
    }.items():
        present = _columns(table)
        for name in names:
            if name in present:
                op.drop_column(table, name)

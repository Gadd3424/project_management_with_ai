"""Project memberships, invitations, chat, and read state."""

import uuid
from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op

from apps.api.app.models import ProjectMember, ProjectMessage

revision = "0005_project_collaboration"
down_revision = "0004_task_management"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    ProjectMember.__table__.create(bind, checkfirst=True)
    ProjectMessage.__table__.create(bind, checkfirst=True)
    projects = bind.execute(sa.text("SELECT id, organization_id, created_by FROM projects WHERE deleted_at IS NULL"))
    now = datetime.now(UTC)
    for project in projects:
        exists = bind.execute(
            sa.text("SELECT 1 FROM project_members WHERE project_id = :project_id AND user_id = :user_id"),
            {"project_id": project.id, "user_id": project.created_by},
        ).first()
        if not exists:
            bind.execute(
                sa.text(
                    """INSERT INTO project_members
                    (id, organization_id, project_id, user_id, role, invitation_status,
                     invited_by, invited_at, joined_at, created_at, updated_at, deleted_at, version)
                    VALUES (:id, :organization_id, :project_id, :user_id, 'project_admin', 'accepted',
                            :user_id, :now, :now, :now, :now, NULL, 1)"""
                ),
                {
                    "id": str(uuid.uuid4()),
                    "organization_id": project.organization_id,
                    "project_id": project.id,
                    "user_id": project.created_by,
                    "now": now,
                },
            )


def downgrade() -> None:
    bind = op.get_bind()
    ProjectMessage.__table__.drop(bind, checkfirst=True)
    ProjectMember.__table__.drop(bind, checkfirst=True)

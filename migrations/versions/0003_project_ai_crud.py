"""Project lifecycle fields and project-scoped AI suggestions."""

import sqlalchemy as sa
from alembic import op

from apps.api.app.models import ProjectAISuggestion

revision = "0003_project_ai_crud"
down_revision = "0002_user_management"
branch_labels = None
depends_on = None


def _columns(table: str) -> set[str]:
    return {column["name"] for column in sa.inspect(op.get_bind()).get_columns(table)}


def _add(table: str, column: sa.Column) -> None:
    if column.name not in _columns(table):
        op.add_column(table, column)


def upgrade() -> None:
    _add("projects", sa.Column("objective", sa.Text(), nullable=False, server_default=""))
    _add("projects", sa.Column("success_criteria", sa.Text(), nullable=False, server_default=""))
    _add("projects", sa.Column("start_date", sa.DateTime(timezone=True), nullable=True))
    _add("projects", sa.Column("due_date", sa.DateTime(timezone=True), nullable=True))
    ProjectAISuggestion.__table__.create(op.get_bind(), checkfirst=True)


def downgrade() -> None:
    ProjectAISuggestion.__table__.drop(op.get_bind(), checkfirst=True)
    existing = _columns("projects")
    for name in ("due_date", "start_date", "success_criteria", "objective"):
        if name in existing:
            op.drop_column("projects", name)


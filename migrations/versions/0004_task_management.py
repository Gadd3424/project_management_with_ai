"""Task notes and four-state kanban workflow."""

import sqlalchemy as sa
from alembic import op

revision = "0004_task_management"
down_revision = "0003_project_ai_crud"
branch_labels = None
depends_on = None


def _columns(table: str) -> set[str]:
    return {column["name"] for column in sa.inspect(op.get_bind()).get_columns(table)}


def upgrade() -> None:
    if "notes" not in _columns("tasks"):
        op.add_column("tasks", sa.Column("notes", sa.Text(), nullable=False, server_default=""))
    op.execute(sa.text("UPDATE tasks SET status = 'on_hold' WHERE status = 'review'"))


def downgrade() -> None:
    op.execute(sa.text("UPDATE tasks SET status = 'review' WHERE status = 'on_hold'"))
    if "notes" in _columns("tasks"):
        op.drop_column("tasks", "notes")

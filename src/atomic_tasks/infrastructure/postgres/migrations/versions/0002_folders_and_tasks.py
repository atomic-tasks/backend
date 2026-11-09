"""folders and tasks

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-09 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Таблицы folders и tasks, затем корень каждому существующему пользователю."""
    op.create_table(
        "folders",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("parent_id", sa.Uuid(), nullable=True),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("weight", sa.Numeric(precision=3, scale=2), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["owner_id"], ["users.id"], name=op.f("fk_folders_owner_id_users"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["parent_id"],
            ["folders.id"],
            name=op.f("fk_folders_parent_id_folders"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_folders")),
    )
    op.create_index("ix_folders_owner_id_parent_id", "folders", ["owner_id", "parent_id"])
    op.create_index("ix_folders_parent_id", "folders", ["parent_id"])
    op.create_index(
        "uq_folders_owner_id_root",
        "folders",
        ["owner_id"],
        unique=True,
        postgresql_where=sa.text("parent_id IS NULL"),
    )
    op.create_table(
        "tasks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("folder_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("weight", sa.Numeric(precision=3, scale=2), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["folder_id"],
            ["folders.id"],
            name=op.f("fk_tasks_folder_id_folders"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["owner_id"], ["users.id"], name=op.f("fk_tasks_owner_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tasks")),
    )
    op.create_index("ix_tasks_owner_id_folder_id", "tasks", ["owner_id", "folder_id"])
    op.create_index("ix_tasks_folder_id", "tasks", ["folder_id"])

    # Корень каждому существующему пользователю.
    # Значения — копия Folder.new_root на момент миграции.
    op.execute(
        """
        INSERT INTO folders
            (id, owner_id, parent_id, title, description, weight, status, created_at, updated_at)
        SELECT uuidv7(), id, NULL, 'Root', NULL, 1.00, 'active', now(), now()
        FROM users
        """,
    )


def downgrade() -> None:
    """Удаляет таблицы; задачи раньше папок из-за внешнего ключа."""
    op.drop_index("ix_tasks_folder_id", table_name="tasks")
    op.drop_index("ix_tasks_owner_id_folder_id", table_name="tasks")
    op.drop_table("tasks")
    op.drop_index("uq_folders_owner_id_root", table_name="folders")
    op.drop_index("ix_folders_parent_id", table_name="folders")
    op.drop_index("ix_folders_owner_id_parent_id", table_name="folders")
    op.drop_table("folders")

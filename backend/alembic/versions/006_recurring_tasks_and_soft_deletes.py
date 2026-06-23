"""recurring tasks and soft deletes

Revision ID: 006
Revises: 005
Create Date: 2026-06-22
"""
from alembic import op
import sqlalchemy as sa

revision = "006"
down_revision = "005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- tasks: soft delete ---
    op.add_column("tasks", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True), schema="organizer")

    # --- task_completions: one row per recurring occurrence completed ---
    op.create_table(
        "task_completions",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("task_id", sa.Integer, sa.ForeignKey("organizer.tasks.id", ondelete="CASCADE"), nullable=False),
        sa.Column("occurrence_date", sa.Date, nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("task_id", "occurrence_date", name="uq_task_completions_task_occurrence"),
        schema="organizer",
    )
    op.create_index("idx_task_completions_task_id", "task_completions", ["task_id"], schema="organizer")

    # --- notes: soft delete ---
    op.add_column("notes", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True), schema="organizer")

    # --- shopping_items: soft delete ---
    op.add_column("shopping_items", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True), schema="organizer")

    # --- wishlist_items: soft delete + promotion tracking ---
    op.add_column("wishlist_items", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True), schema="organizer")
    op.add_column("wishlist_items", sa.Column("promoted_at", sa.DateTime(timezone=True), nullable=True), schema="organizer")


def downgrade() -> None:
    op.drop_column("wishlist_items", "promoted_at", schema="organizer")
    op.drop_column("wishlist_items", "deleted_at", schema="organizer")
    op.drop_column("shopping_items", "deleted_at", schema="organizer")
    op.drop_column("notes", "deleted_at", schema="organizer")
    op.drop_index("idx_task_completions_task_id", "task_completions", schema="organizer")
    op.drop_table("task_completions", schema="organizer")
    op.drop_column("tasks", "deleted_at", schema="organizer")

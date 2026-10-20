"""Create metrics schema (series, entries, tags)

Personal measurement log: durations (start/stop), values and counts. All FKs are RESTRICT so
nothing is ever cascade-deleted; entries are discarded and series archived instead.

Revision ID: 073
Revises: 072
Create Date: 2026-10-21
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "073"
down_revision = "072"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS metrics")

    op.create_table(
        "series",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(64), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("unit", sa.String(20), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_archived", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name", name="uq_metric_series_name"),
        sa.CheckConstraint("kind IN ('duration', 'value', 'count')", name="ck_metric_series_kind"),
        schema="metrics",
    )
    op.create_index("ix_metrics_series_id", "series", ["id"], schema="metrics")

    op.create_table(
        "tags",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        schema="metrics",
    )
    op.create_index("ix_metrics_tags_id", "tags", ["id"], schema="metrics")
    op.execute("CREATE UNIQUE INDEX uq_metric_tags_name_lower ON metrics.tags (lower(name))")

    op.create_table(
        "entries",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("series_id", sa.Integer(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("value", sa.Numeric(), nullable=True),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("source", sa.String(16), nullable=False),
        sa.Column("start_lat", sa.Float(), nullable=True),
        sa.Column("start_lon", sa.Float(), nullable=True),
        sa.Column("start_accuracy_m", sa.Float(), nullable=True),
        sa.Column("end_lat", sa.Float(), nullable=True),
        sa.Column("end_lon", sa.Float(), nullable=True),
        sa.Column("end_accuracy_m", sa.Float(), nullable=True),
        sa.Column("context", postgresql.JSONB(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["series_id"], ["metrics.series.id"], ondelete="RESTRICT"),
        sa.CheckConstraint("status IN ('open', 'closed', 'discarded')", name="ck_metric_entries_status"),
        sa.CheckConstraint("source IN ('telegram', 'shortcut', 'portal', 'mcp')", name="ck_metric_entries_source"),
        sa.CheckConstraint("ended_at IS NULL OR ended_at >= started_at", name="ck_metric_entries_ended_after_start"),
        sa.CheckConstraint(
            "(start_lat IS NULL OR start_lat BETWEEN -90 AND 90) AND (end_lat IS NULL OR end_lat BETWEEN -90 AND 90)"
            " AND (start_lon IS NULL OR start_lon BETWEEN -180 AND 180)"
            " AND (end_lon IS NULL OR end_lon BETWEEN -180 AND 180)",
            name="ck_metric_entries_coordinates",
        ),
        schema="metrics",
    )
    op.create_index("ix_metrics_entries_id", "entries", ["id"], schema="metrics")
    op.create_index("ix_metric_entries_series_started", "entries", ["series_id", "started_at"], schema="metrics")
    op.create_index(
        "ix_metric_entries_open",
        "entries",
        ["series_id"],
        schema="metrics",
        postgresql_where=sa.text("status = 'open'"),
    )

    op.create_table(
        "entries_tags",
        sa.Column("entry_id", sa.Integer(), nullable=False),
        sa.Column("tag_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["entry_id"], ["metrics.entries.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["tag_id"], ["metrics.tags.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("entry_id", "tag_id"),
        schema="metrics",
    )
    op.create_index("ix_metrics_entries_tags_tag_id", "entries_tags", ["tag_id"], schema="metrics")


def downgrade() -> None:
    op.drop_table("entries_tags", schema="metrics")
    op.drop_table("entries", schema="metrics")
    op.drop_table("tags", schema="metrics")
    op.drop_table("series", schema="metrics")
    op.execute("DROP SCHEMA IF EXISTS metrics")

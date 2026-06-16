"""initial schema

Revision ID: 001
Revises:
Create Date: 2026-06-13
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.execute("CREATE SCHEMA IF NOT EXISTS core")
    op.execute("CREATE SCHEMA IF NOT EXISTS organizer")
    op.execute("CREATE SCHEMA IF NOT EXISTS monitoring")
    op.execute("CREATE SCHEMA IF NOT EXISTS finance")
    op.execute("CREATE SCHEMA IF NOT EXISTS integration")

    # --- core ---
    op.create_table(
        "sessions",
        sa.Column("id", sa.Integer, primary_key=True, index=True),
        sa.Column("source", sa.String(50), nullable=True),
        sa.Column("external_id", sa.String(255), nullable=True),
        sa.Column("summary", sa.Text, nullable=True),
        sa.Column("last_interaction_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        schema="core",
    )
    op.create_index("idx_sessions_source_external_id", "sessions", ["source", "external_id"], schema="core")

    op.create_table(
        "messages",
        sa.Column("id", sa.Integer, primary_key=True, index=True),
        sa.Column("session_id", sa.Integer, sa.ForeignKey("core.sessions.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("meta", JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        schema="core",
    )

    op.create_table(
        "memories",
        sa.Column("id", sa.Integer, primary_key=True, index=True),
        sa.Column("category", sa.String(50), nullable=False, index=True),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("importance", sa.Float, nullable=False),
        sa.Column("confidence", sa.Float, nullable=False),
        sa.Column("active", sa.Boolean, nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("extra_metadata", JSONB, nullable=True),
        sa.Column("origin_message_id", sa.Integer, sa.ForeignKey("core.messages.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        schema="core",
    )

    op.create_table(
        "working_memory",
        sa.Column("id", sa.Integer, primary_key=True, index=True),
        sa.Column("key", sa.String(255), nullable=False, index=True),
        sa.Column("value", sa.Text, nullable=False),
        sa.Column("importance", sa.Float, nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True, index=True),
        sa.Column("session_id", sa.Integer, sa.ForeignKey("core.sessions.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        schema="core",
    )

    op.execute("""
        CREATE TABLE core.embeddings (
            id          SERIAL PRIMARY KEY,
            source_type VARCHAR(100)             NOT NULL,
            source_id   INTEGER                  NOT NULL,
            content     TEXT                     NOT NULL,
            embedding   vector(384)              NOT NULL,
            model       VARCHAR(100)             NOT NULL,
            dimensions  INTEGER                  NOT NULL,
            embedded_at TIMESTAMPTZ              NOT NULL DEFAULT now()
        )
    """)
    op.execute("CREATE INDEX ix_core_embeddings_id ON core.embeddings (id)")
    op.execute("CREATE INDEX ix_core_embeddings_source_type ON core.embeddings (source_type)")
    op.execute("CREATE INDEX ix_core_embeddings_source_id ON core.embeddings (source_id)")

    op.create_table(
        "command_executions",
        sa.Column("id", sa.Integer, primary_key=True, index=True),
        sa.Column("message_id", sa.Integer, sa.ForeignKey("core.messages.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("command_name", sa.String(100), nullable=False, index=True),
        sa.Column("entities", JSONB, nullable=True),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("error", sa.Text, nullable=True),
        sa.Column("entity_type", sa.String(100), nullable=True),
        sa.Column("entity_id", sa.Integer, nullable=True),
        sa.Column("executed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        schema="core",
    )

    # --- integration ---
    op.create_table(
        "llm_calls",
        sa.Column("id", sa.Integer, primary_key=True, index=True),
        sa.Column("provider", sa.String(50), nullable=False),
        sa.Column("model", sa.String(100), nullable=False),
        sa.Column("feature", sa.String(100), nullable=False),
        sa.Column("prompt", JSONB, nullable=False),
        sa.Column("response", sa.Text, nullable=False),
        sa.Column("tokens_input", sa.Integer, nullable=True),
        sa.Column("tokens_output", sa.Integer, nullable=True),
        sa.Column("latency_ms", sa.Integer, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        schema="integration",
    )
    op.create_table(
        "provider_calls",
        sa.Column("id", sa.Integer, primary_key=True, index=True),
        sa.Column("provider", sa.String(50), nullable=False),
        sa.Column("operation", sa.String(50), nullable=False),
        sa.Column("entity_type", sa.String(100), nullable=False),
        sa.Column("provider_entity_id", sa.String(255), nullable=True),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("request_payload", JSONB, nullable=True),
        sa.Column("response_payload", JSONB, nullable=True),
        sa.Column("error", sa.Text, nullable=True),
        sa.Column("command_execution_id", sa.Integer, sa.ForeignKey("core.command_executions.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        schema="integration",
    )

    # --- organizer ---
    op.create_table(
        "tags",
        sa.Column("id", sa.Integer, primary_key=True, index=True),
        sa.Column("provider_id", sa.String(255), nullable=False),
        sa.Column("name", sa.String(255), nullable=False, index=True),
        sa.UniqueConstraint("provider_id", "name", name="uq_provider_tag_name"),
        schema="organizer",
    )

    op.create_table(
        "calendar_events",
        sa.Column("id", sa.Integer, primary_key=True, index=True),
        sa.Column("provider_id", sa.String(255), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("location", sa.String(500), nullable=True),
        sa.Column("start_datetime", sa.DateTime, nullable=False),
        sa.Column("end_datetime", sa.DateTime, nullable=False),
        sa.Column("all_day", sa.Boolean, nullable=False),
        sa.Column("recurrence_rule", sa.String(500), nullable=True),
        sa.Column("host", sa.String(255), nullable=True),
        sa.UniqueConstraint("provider_id", name="uq_calendar_events_provider_id"),
        schema="organizer",
    )

    op.create_table(
        "calendar_event_invitees",
        sa.Column("id", sa.Integer, primary_key=True, index=True),
        sa.Column("event_id", sa.Integer, sa.ForeignKey("organizer.calendar_events.id", ondelete="CASCADE"), nullable=False),
        sa.Column("email", sa.String(255), nullable=False),
        schema="organizer",
    )

    op.create_table(
        "tasks",
        sa.Column("id", sa.Integer, primary_key=True, index=True),
        sa.Column("provider_id", sa.String(255), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("status", sa.String(255), nullable=False),
        sa.Column("priority", sa.String(255), nullable=False),
        sa.Column("urgency", sa.String(255), nullable=False),
        sa.Column("deadline", sa.DateTime, nullable=True),
        sa.Column("recurrence_rule", sa.String(255), nullable=True),
        sa.UniqueConstraint("provider_id", name="uq_tasks_provider_id"),
        schema="organizer",
    )

    op.create_table(
        "notes",
        sa.Column("id", sa.Integer, primary_key=True, index=True),
        sa.Column("provider_id", sa.String(255), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.UniqueConstraint("provider_id", name="uq_notes_provider_id"),
        schema="organizer",
    )

    op.create_table(
        "tasks_tags",
        sa.Column("task_id", sa.Integer, sa.ForeignKey("organizer.tasks.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("tag_id", sa.Integer, sa.ForeignKey("organizer.tags.id", ondelete="CASCADE"), primary_key=True),
        schema="organizer",
    )

    op.create_table(
        "notes_tags",
        sa.Column("note_id", sa.Integer, sa.ForeignKey("organizer.notes.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("tag_id", sa.Integer, sa.ForeignKey("organizer.tags.id", ondelete="CASCADE"), primary_key=True),
        schema="organizer",
    )

    op.create_table(
        "calendar_events_tags",
        sa.Column("event_id", sa.Integer, sa.ForeignKey("organizer.calendar_events.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("tag_id", sa.Integer, sa.ForeignKey("organizer.tags.id", ondelete="CASCADE"), primary_key=True),
        schema="organizer",
    )

    # --- monitoring ---
    op.create_table(
        "configs",
        sa.Column("id", sa.Integer, primary_key=True, index=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("enabled", sa.Boolean, nullable=False),
        sa.Column("type", sa.String(50), nullable=False),
        sa.Column("url", sa.String(255), nullable=False),
        sa.Column("selector", sa.String(255), nullable=True),
        sa.Column("json_path", sa.String(255), nullable=True),
        sa.Column("target", sa.String(255), nullable=False),
        sa.Column("case_sensitive", sa.Boolean, nullable=False),
        sa.Column("timeout", sa.Integer, nullable=False),
        sa.Column("page_size", sa.Integer, nullable=True),
        sa.Column("max_pages", sa.Integer, nullable=True),
        sa.Column("request_delay", sa.Integer, nullable=True),
        sa.Column("wait_selector", sa.String(255), nullable=True),
        sa.UniqueConstraint("name", name="uq_monitoring_configs_name"),
        schema="monitoring",
    )

    op.create_table(
        "executions",
        sa.Column("id", sa.Integer, primary_key=True, index=True),
        sa.Column("config_id", sa.Integer, sa.ForeignKey("monitoring.configs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("result", sa.Text, nullable=True),
        sa.Column("error", sa.Text, nullable=True),
        sa.Column("config_snapshot", JSONB, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        schema="monitoring",
    )

    op.create_table(
        "alerts",
        sa.Column("id", sa.Integer, primary_key=True, index=True),
        sa.Column("execution_id", sa.Integer, sa.ForeignKey("monitoring.executions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        schema="monitoring",
    )

    # --- finance ---
    op.create_table(
        "accounts",
        sa.Column("id", sa.Integer, primary_key=True, index=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("type", sa.String(50), nullable=False),
        sa.Column("currency", sa.String(10), nullable=False),
        sa.Column("balance", sa.Numeric(12, 2), nullable=False),
        sa.Column("institution", sa.String(255), nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False),
        schema="finance",
    )

    op.create_table(
        "categories",
        sa.Column("id", sa.Integer, primary_key=True, index=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("parent_id", sa.Integer, sa.ForeignKey("finance.categories.id", ondelete="SET NULL"), nullable=True),
        schema="finance",
    )

    op.create_table(
        "budgets",
        sa.Column("id", sa.Integer, primary_key=True, index=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("category_id", sa.Integer, sa.ForeignKey("finance.categories.id", ondelete="SET NULL"), nullable=True),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("period", sa.String(20), nullable=False),
        sa.Column("starts_at", sa.DateTime, nullable=True),
        sa.Column("ends_at", sa.DateTime, nullable=True),
        schema="finance",
    )

    op.create_table(
        "transactions",
        sa.Column("id", sa.Integer, primary_key=True, index=True),
        sa.Column("account_id", sa.Integer, sa.ForeignKey("finance.accounts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("date", sa.DateTime, nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("currency", sa.String(10), nullable=False),
        sa.Column("type", sa.String(20), nullable=False),
        sa.Column("category_id", sa.Integer, sa.ForeignKey("finance.categories.id", ondelete="SET NULL"), nullable=True),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("merchant", sa.String(255), nullable=True),
        sa.Column("source", sa.String(50), nullable=True),
        sa.Column("deduplication_hash", sa.String(64), nullable=True, unique=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now(), nullable=False),
        schema="finance",
    )

    op.create_table(
        "recurring_transactions",
        sa.Column("id", sa.Integer, primary_key=True, index=True),
        sa.Column("account_id", sa.Integer, sa.ForeignKey("finance.accounts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("category_id", sa.Integer, sa.ForeignKey("finance.categories.id", ondelete="SET NULL"), nullable=True),
        sa.Column("type", sa.String(20), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("currency", sa.String(10), nullable=False),
        sa.Column("merchant", sa.String(255), nullable=True),
        sa.Column("recurrence_rule", sa.String(255), nullable=False),
        sa.Column("active", sa.Boolean, nullable=False),
        schema="finance",
    )


def downgrade() -> None:
    # Association tables first (no other tables depend on them)
    op.drop_table("calendar_events_tags", schema="organizer")
    op.drop_table("notes_tags", schema="organizer")
    op.drop_table("tasks_tags", schema="organizer")

    # finance
    op.drop_table("recurring_transactions", schema="finance")
    op.drop_table("transactions", schema="finance")
    op.drop_table("budgets", schema="finance")
    op.drop_table("categories", schema="finance")
    op.drop_table("accounts", schema="finance")

    # monitoring
    op.drop_table("alerts", schema="monitoring")
    op.drop_table("executions", schema="monitoring")
    op.drop_table("configs", schema="monitoring")

    # organizer (dependents before parents)
    op.drop_table("notes", schema="organizer")
    op.drop_table("calendar_event_invitees", schema="organizer")
    op.drop_table("tasks", schema="organizer")
    op.drop_table("calendar_events", schema="organizer")
    op.drop_table("tags", schema="organizer")

    # integration (depends on core.command_executions)
    op.drop_table("llm_calls", schema="integration")
    op.drop_table("provider_calls", schema="integration")

    # core (dependents before parents)
    op.execute("DROP TABLE IF EXISTS core.embeddings")
    op.drop_table("memories", schema="core")
    op.drop_table("command_executions", schema="core")
    op.drop_table("working_memory", schema="core")
    op.drop_table("messages", schema="core")
    op.drop_table("sessions", schema="core")

    op.execute("DROP SCHEMA IF EXISTS integration")
    op.execute("DROP SCHEMA IF EXISTS finance")
    op.execute("DROP SCHEMA IF EXISTS monitoring")
    op.execute("DROP SCHEMA IF EXISTS organizer")
    op.execute("DROP SCHEMA IF EXISTS core")

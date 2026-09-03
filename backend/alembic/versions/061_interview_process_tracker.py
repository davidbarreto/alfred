"""Add interview process tracker tables

Tracks job-interview pipelines: companies interviewed with, application
processes (role, compensation/logistics, status), the stages within each
process (phone screen, code review, live coding, onsite, behavioral, system
design, offer, other), and lightweight join tables linking a stage to
existing organizer.contacts (recruiters/interviewers), organizer.tasks and
organizer.notes -- no changes needed to those tables themselves.
interview_processes.study_plan_id is an optional cross-schema link to
cs.study_plans so interview prep can be tied to a process without coupling
the two feature areas. interview_links stores external references (job
posting, resume used, offer letter) as plain URLs -- no file storage exists
in this codebase yet. interview_insights persists AI-generated weekly-focus
recommendations across active processes.

Revision ID: 061
Revises: 060
Create Date: 2026-09-03
"""
from alembic import op
import sqlalchemy as sa

revision = "061"
down_revision = "060"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "interview_companies",
        sa.Column("id", sa.Integer, primary_key=True, index=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("website", sa.String(500), nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
            nullable=False,
        ),
        schema="organizer",
    )

    op.create_table(
        "interview_processes",
        sa.Column("id", sa.Integer, primary_key=True, index=True),
        sa.Column(
            "company_id",
            sa.Integer,
            sa.ForeignKey("organizer.interview_companies.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("role_title", sa.String(255), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("source", sa.String(100), nullable=True),
        sa.Column("applied_date", sa.Date, nullable=True),
        sa.Column("priority", sa.String(10), nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column(
            "study_plan_id",
            sa.Integer,
            sa.ForeignKey("cs.study_plans.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("salary_min", sa.Integer, nullable=True),
        sa.Column("salary_max", sa.Integer, nullable=True),
        sa.Column("salary_currency", sa.String(3), nullable=True),
        sa.Column("work_regime", sa.String(20), nullable=True),
        sa.Column("office_days_per_month", sa.Numeric(4, 1), nullable=True),
        sa.Column("office_location", sa.String(255), nullable=True),
        sa.Column("benefits", sa.Text, nullable=True),
        sa.Column("job_description_url", sa.String(1000), nullable=True),
        sa.Column("company_feedback", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
            nullable=False,
        ),
        schema="organizer",
    )

    op.create_table(
        "interview_stages",
        sa.Column("id", sa.Integer, primary_key=True, index=True),
        sa.Column(
            "process_id",
            sa.Integer,
            sa.ForeignKey("organizer.interview_processes.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("stage_type", sa.String(30), nullable=False),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="scheduled"),
        sa.Column("feedback", sa.Text, nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("sequence", sa.Integer, nullable=False, server_default="0"),
        sa.Column(
            "calendar_event_id",
            sa.Integer,
            sa.ForeignKey("organizer.calendar_events.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
            nullable=False,
        ),
        schema="organizer",
    )

    op.create_table(
        "interview_stage_contacts",
        sa.Column(
            "stage_id",
            sa.Integer,
            sa.ForeignKey("organizer.interview_stages.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "contact_id",
            sa.Integer,
            sa.ForeignKey("organizer.contacts.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("role", sa.String(50), nullable=True),
        schema="organizer",
    )

    op.create_table(
        "interview_links",
        sa.Column("id", sa.Integer, primary_key=True, index=True),
        sa.Column(
            "process_id",
            sa.Integer,
            sa.ForeignKey("organizer.interview_processes.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("url", sa.String(1000), nullable=False),
        sa.Column("label", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        schema="organizer",
    )

    op.create_table(
        "interview_stage_tasks",
        sa.Column(
            "stage_id",
            sa.Integer,
            sa.ForeignKey("organizer.interview_stages.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "task_id",
            sa.Integer,
            sa.ForeignKey("organizer.tasks.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        schema="organizer",
    )

    op.create_table(
        "interview_stage_notes",
        sa.Column(
            "stage_id",
            sa.Integer,
            sa.ForeignKey("organizer.interview_stages.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "note_id",
            sa.Integer,
            sa.ForeignKey("organizer.notes.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        schema="organizer",
    )

    op.create_table(
        "interview_insights",
        sa.Column("id", sa.Integer, primary_key=True, index=True),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("model", sa.String(100), nullable=False),
        sa.Column("process_ids", sa.JSON, nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        schema="organizer",
    )


def downgrade() -> None:
    op.drop_table("interview_insights", schema="organizer")
    op.drop_table("interview_stage_notes", schema="organizer")
    op.drop_table("interview_stage_tasks", schema="organizer")
    op.drop_table("interview_links", schema="organizer")
    op.drop_table("interview_stage_contacts", schema="organizer")
    op.drop_table("interview_stages", schema="organizer")
    op.drop_table("interview_processes", schema="organizer")
    op.drop_table("interview_companies", schema="organizer")

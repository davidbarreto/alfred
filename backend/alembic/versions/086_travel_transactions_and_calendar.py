"""Link travel legs, stays and visits to finance transactions; remember imported calendar events

A leg (ticket, seat, baggage), a stay (deposit, balance, city tax) and a visit (a meal, an entry)
each get their own link table to finance.transactions; deleting either side removes only the link
row. legs and stays also get a unique calendar_event_id so importing the same calendar event twice
is refused.

Revision ID: 086
Revises: 085
Create Date: 2026-11-10
"""
from alembic import op
import sqlalchemy as sa

revision = "086"
down_revision = "085"
branch_labels = None
depends_on = None

_SCHEMA = "travel"
_LINKS = (("legs_transactions", "leg_id", "legs"), ("stays_transactions", "stay_id", "stays"), ("visits_transactions", "visit_id", "visits"))


def upgrade() -> None:
    for table, column, parent in _LINKS:
        op.create_table(
            table,
            sa.Column(column, sa.Integer(), nullable=False),
            sa.Column("transaction_id", sa.Integer(), nullable=False),
            sa.ForeignKeyConstraint([column], [f"travel.{parent}.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["transaction_id"], ["finance.transactions.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint(column, "transaction_id"),
            schema=_SCHEMA,
        )
        op.create_index(f"ix_travel_{table}_transaction_id", table, ["transaction_id"], schema=_SCHEMA)

    for table in ("legs", "stays"):
        op.add_column(
            table,
            sa.Column(
                "calendar_event_id", sa.Integer(), sa.ForeignKey("organizer.calendar_events.id", ondelete="SET NULL"),
                nullable=True,
            ),
            schema=_SCHEMA,
        )
        op.create_unique_constraint(f"uq_travel_{table}_calendar_event_id", table, ["calendar_event_id"], schema=_SCHEMA)


def downgrade() -> None:
    for table in ("stays", "legs"):
        op.drop_constraint(f"uq_travel_{table}_calendar_event_id", table, schema=_SCHEMA, type_="unique")
        op.drop_column(table, "calendar_event_id", schema=_SCHEMA)
    for table, _column, _parent in reversed(_LINKS):
        op.drop_table(table, schema=_SCHEMA)

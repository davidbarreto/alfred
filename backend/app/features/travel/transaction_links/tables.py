from sqlalchemy import Column, ForeignKey, Table

from app.db.base import Base

# Deleting either side removes only the link row: a transaction survives its trip, a trip survives its transactions.
legs_transactions = Table(
    "legs_transactions",
    Base.metadata,
    Column("leg_id", ForeignKey("travel.legs.id", ondelete="CASCADE"), primary_key=True),
    Column("transaction_id", ForeignKey("finance.transactions.id", ondelete="CASCADE"), primary_key=True, index=True),
    schema="travel",
)

stays_transactions = Table(
    "stays_transactions",
    Base.metadata,
    Column("stay_id", ForeignKey("travel.stays.id", ondelete="CASCADE"), primary_key=True),
    Column("transaction_id", ForeignKey("finance.transactions.id", ondelete="CASCADE"), primary_key=True, index=True),
    schema="travel",
)

visits_transactions = Table(
    "visits_transactions",
    Base.metadata,
    Column("visit_id", ForeignKey("travel.visits.id", ondelete="CASCADE"), primary_key=True),
    Column("transaction_id", ForeignKey("finance.transactions.id", ondelete="CASCADE"), primary_key=True, index=True),
    schema="travel",
)

# kind -> (link table, name of its entity column)
LINK_TABLES = {
    "legs": (legs_transactions, "leg_id"),
    "stays": (stays_transactions, "stay_id"),
    "visits": (visits_transactions, "visit_id"),
}

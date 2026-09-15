from sqlalchemy import Integer, String, ForeignKey, Table, Column
from sqlalchemy.orm import relationship, Mapped, mapped_column
from typing import List, TYPE_CHECKING
from app.db.base import Base

if TYPE_CHECKING:
    from app.features.finance.transactions.tables import Transaction


# Association table for Transaction-Tag relationship
transactions_tags = Table(
    "transactions_tags",
    Base.metadata,
    Column("transaction_id", Integer, ForeignKey("finance.transactions.id", ondelete="CASCADE"), primary_key=True),
    Column("tag_id", Integer, ForeignKey("finance.tags.id", ondelete="CASCADE"), primary_key=True),
    schema="finance",
)


class FinanceTag(Base):
    """A free-form context label spanning categories (e.g. "Travel", "Work") --
    unlike Category, which is exclusive per transaction, a transaction can carry
    several tags at once. See categories.tables.Category for the exclusive-hierarchy
    counterpart this deliberately doesn't reuse.

    Named FinanceTag (not Tag) purely to avoid a SQLAlchemy declarative-registry
    class-name collision with organizer.tags.tables.Tag -- the two are unrelated
    (this one isn't Notion-scoped by provider_id). The table itself is still
    "finance.tags"; only the Python class needs a distinct identifier."""

    __tablename__ = "tags"
    __table_args__ = {"schema": "finance"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)

    transactions: Mapped[List["Transaction"]] = relationship(
        "app.features.finance.transactions.tables.Transaction",
        secondary=transactions_tags,
        back_populates="tags",
    )

from datetime import datetime
from decimal import Decimal

from sqlalchemy import Select, and_, case, func, literal, select, union
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.finance.tags.tables import FinanceTag, transactions_tags
from app.features.finance.transactions.tables import Transaction
from app.features.travel.legs.tables import Leg
from app.features.travel.places.tables import Place
from app.features.travel.stays.tables import Stay
from app.features.travel.transaction_links.tables import LINK_TABLES, legs_transactions, stays_transactions, visits_transactions
from app.features.travel.visits.tables import Visit

_ENTITIES = {"legs": Leg, "stays": Stay, "visits": Visit}


def _signed_eur():
    """Expenses add to a cost, refunds (income) take away from it."""
    magnitude = func.abs(Transaction.amount_eur)
    return case((Transaction.type == "income", -magnitude), else_=magnitude)


def _sum_columns():
    return (
        func.coalesce(func.sum(_signed_eur()), 0),
        func.count(),
        func.count().filter(Transaction.amount_eur.is_(None)),
    )


def _row_to_cost(total, count, unconverted) -> tuple[Decimal, int, int]:
    return Decimal(total or 0).quantize(Decimal("0.01")), int(count), int(unconverted)


class TransactionLinkRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def entity_exists(self, kind: str, entity_id: int) -> bool:
        return await self._session.get(_ENTITIES[kind], entity_id) is not None

    async def get_transaction(self, transaction_id: int) -> Transaction | None:
        return await self._session.get(Transaction, transaction_id)

    async def link(self, kind: str, entity_id: int, transaction_id: int) -> None:
        table, column = LINK_TABLES[kind]
        stmt = pg_insert(table).values({column: entity_id, "transaction_id": transaction_id}).on_conflict_do_nothing()
        await self._session.execute(stmt)
        await self._session.commit()

    async def unlink(self, kind: str, entity_id: int, transaction_id: int) -> bool:
        table, column = LINK_TABLES[kind]
        result = await self._session.execute(
            table.delete().where(table.c[column] == entity_id, table.c.transaction_id == transaction_id)
        )
        await self._session.commit()
        return result.rowcount > 0

    async def get_linked(self, kind: str, entity_id: int) -> list[Transaction]:
        table, column = LINK_TABLES[kind]
        stmt = (
            select(Transaction)
            .join(table, table.c.transaction_id == Transaction.id)
            .where(table.c[column] == entity_id)
            .order_by(Transaction.date, Transaction.id)
        )
        return list((await self._session.scalars(stmt)).all())

    async def get_entity_costs(self, kind: str, entity_ids: list[int]) -> dict[int, tuple[Decimal, int, int]]:
        if not entity_ids:
            return {}
        table, column = LINK_TABLES[kind]
        stmt = (
            select(table.c[column], *_sum_columns())
            .select_from(table.join(Transaction, Transaction.id == table.c.transaction_id))
            .where(table.c[column].in_(entity_ids))
            .group_by(table.c[column])
        )
        return {row[0]: _row_to_cost(*row[1:]) for row in (await self._session.execute(stmt)).all()}

    async def get_linked_ids(self, kind: str, entity_ids: list[int]) -> set[int]:
        """Which of these legs, stays or visits have at least one linked transaction."""
        if not entity_ids:
            return set()
        table, column = LINK_TABLES[kind]
        stmt = select(table.c[column]).where(table.c[column].in_(entity_ids)).distinct()
        return set((await self._session.scalars(stmt)).all())

    def _trip_transaction_ids(self, trip_id: int) -> Select:
        """Distinct transactions linked anywhere in a trip."""
        return union(
            select(legs_transactions.c.transaction_id)
            .join(Leg, Leg.id == legs_transactions.c.leg_id).where(Leg.trip_id == trip_id),
            select(stays_transactions.c.transaction_id)
            .join(Stay, Stay.id == stays_transactions.c.stay_id).where(Stay.trip_id == trip_id),
            select(visits_transactions.c.transaction_id)
            .join(Visit, Visit.id == visits_transactions.c.visit_id).where(Visit.trip_id == trip_id),
        )

    async def get_trip_total(self, trip_id: int) -> tuple[Decimal, int, int]:
        ids = self._trip_transaction_ids(trip_id).subquery()
        stmt = select(*_sum_columns()).select_from(Transaction).where(Transaction.id.in_(select(ids.c.transaction_id)))
        return _row_to_cost(*(await self._session.execute(stmt)).one())

    async def get_trip_costs_by_kind(self, trip_id: int) -> dict[str, tuple[Decimal, int, int]]:
        kinds = union(
            select(Leg.mode.label("kind"), legs_transactions.c.transaction_id.label("transaction_id"))
            .join(Leg, Leg.id == legs_transactions.c.leg_id).where(Leg.trip_id == trip_id),
            select(literal("lodging").label("kind"), stays_transactions.c.transaction_id.label("transaction_id"))
            .join(Stay, Stay.id == stays_transactions.c.stay_id).where(Stay.trip_id == trip_id),
            select(Place.kind.label("kind"), visits_transactions.c.transaction_id.label("transaction_id"))
            .join(Visit, Visit.id == visits_transactions.c.visit_id)
            .join(Place, Place.id == Visit.place_id).where(Visit.trip_id == trip_id),
        ).subquery()
        stmt = (
            select(kinds.c.kind, *_sum_columns())
            .select_from(kinds.join(Transaction, Transaction.id == kinds.c.transaction_id))
            .group_by(kinds.c.kind)
            .order_by(kinds.c.kind)
        )
        return {row[0]: _row_to_cost(*row[1:]) for row in (await self._session.execute(stmt)).all()}

    async def get_place_total(self, place_id: int) -> tuple[Decimal, int, int]:
        ids = union(
            select(visits_transactions.c.transaction_id)
            .join(Visit, Visit.id == visits_transactions.c.visit_id).where(Visit.place_id == place_id),
            select(stays_transactions.c.transaction_id)
            .join(Stay, Stay.id == stays_transactions.c.stay_id).where(Stay.place_id == place_id),
        ).subquery()
        stmt = select(*_sum_columns()).select_from(Transaction).where(Transaction.id.in_(select(ids.c.transaction_id)))
        return _row_to_cost(*(await self._session.execute(stmt)).one())

    async def get_unlinked(self, start: datetime, end: datetime, tag_names: list[str]) -> list[Transaction]:
        """Expenses dated in [start, end) that carry none of the tags and that no leg, stay or visit is
        linked to: the ones to tag or link by hand. Tagged charges are listed apart (`get_tagged`)."""
        linked = union(
            select(legs_transactions.c.transaction_id),
            select(stays_transactions.c.transaction_id),
            select(visits_transactions.c.transaction_id),
        ).subquery()
        lowered = [n.lower() for n in tag_names]
        conditions = [
            Transaction.type == "expense",
            Transaction.date >= start,
            Transaction.date < end,
            Transaction.id.not_in(select(linked.c.transaction_id)),
        ]
        if lowered:
            conditions.append(
                Transaction.id.not_in(
                    select(transactions_tags.c.transaction_id)
                    .join(FinanceTag, FinanceTag.id == transactions_tags.c.tag_id)
                    .where(func.lower(FinanceTag.name).in_(lowered))
                )
            )
        stmt = select(Transaction).where(*conditions).order_by(Transaction.date, Transaction.id)
        return list((await self._session.scalars(stmt)).all())

    async def get_tagged(self, tag_names: list[str], start: datetime, end: datetime) -> list[tuple[Transaction, bool]]:
        """Expenses and income dated in [start, end) carrying one of the tags, each with whether a leg, stay or
        visit is linked to it. Transfers are never a trip cost."""
        lowered = [n.lower() for n in tag_names]
        if not lowered:
            return []
        linked = union(
            select(legs_transactions.c.transaction_id),
            select(stays_transactions.c.transaction_id),
            select(visits_transactions.c.transaction_id),
        ).subquery()
        stmt = (
            select(Transaction, Transaction.id.in_(select(linked.c.transaction_id)))
            .where(
                Transaction.type.in_(("expense", "income")),
                Transaction.date >= start,
                Transaction.date < end,
                Transaction.id.in_(
                    select(transactions_tags.c.transaction_id)
                    .join(FinanceTag, FinanceTag.id == transactions_tags.c.tag_id)
                    .where(func.lower(FinanceTag.name).in_(lowered))
                ),
            )
            .order_by(Transaction.date, Transaction.id)
        )
        return [(row[0], bool(row[1])) for row in (await self._session.execute(stmt)).all()]

    async def tag_expenses_between(self, start: datetime, end: datetime, tag_ids: list[int]) -> int:
        """Give every expense dated in [start, end) each tag it does not carry yet; returns the rows added."""
        added = 0
        for tag_id in tag_ids:
            candidates = select(Transaction.id, literal(tag_id)).where(
                and_(Transaction.type == "expense", Transaction.date >= start, Transaction.date < end)
            )
            stmt = pg_insert(transactions_tags).from_select(["transaction_id", "tag_id"], candidates).on_conflict_do_nothing()
            added += (await self._session.execute(stmt)).rowcount
        await self._session.commit()
        return added

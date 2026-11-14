from datetime import date, datetime, time, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from freezegun import freeze_time
from sqlalchemy.dialects import postgresql

from app.features.finance.tags.names import merge_tag_names
from app.features.finance.transactions.schemas import TransactionCreate
from app.features.travel.calendar_import.service import CalendarImportService
from app.features.travel.default_tags import (
    TripDefaultTagService,
    TripTagWindow,
    TripTagWindows,
    parse_default_tag_names,
)
from app.features.travel.errors import TravelConflictError, TravelNotFoundError
from app.features.travel.legs.schemas import LegCreate
from app.features.travel.legs.service import LegService
from app.features.travel.stays.schemas import StayCreate
from app.features.travel.stays.service import StayService
from app.features.travel.transaction_links.repository import TransactionLinkRepository
from app.features.travel.transaction_links.service import TransactionLinkService, TransferNotLinkableError


class TestParseDefaultTagNames:
    def test_splits_trims_and_lowercases_and_dedupes(self):
        assert parse_default_tag_names(" Travel, hotel ,, TRAVEL,Hotel") == ["travel", "hotel"]

    def test_empty_and_none(self):
        assert parse_default_tag_names(None) == []
        assert parse_default_tag_names(" , ") == []


class TestMergeTagNames:
    def test_first_spelling_wins_across_groups(self):
        assert merge_tag_names(["Travel"], ["travel", "Rome"], [" Rome ", "Hotel"]) == ["Travel", "Rome", "Hotel"]

    def test_blank_names_are_dropped(self):
        assert merge_tag_names([], ["", "  "]) == []


class TestTripTagWindows:
    windows = TripTagWindows([
        TripTagWindow(date(2026, 12, 17), date(2026, 12, 24), ["Travel", "Hotel"]),
        TripTagWindow(date(2026, 12, 20), date(2026, 12, 22), ["travel", "Rome"]),
    ])

    def test_expense_inside_the_trip_gets_its_tags(self):
        assert self.windows.names_for(date(2026, 12, 18), "expense") == ["Travel", "Hotel"]

    def test_overlapping_trips_merge_without_duplicates(self):
        assert self.windows.names_for(date(2026, 12, 21), "expense") == ["Travel", "Hotel", "Rome"]

    def test_bounds_are_inclusive_and_outside_is_empty(self):
        assert self.windows.names_for(date(2026, 12, 24), "expense") == ["Travel", "Hotel"]
        assert self.windows.names_for(date(2026, 12, 25), "expense") == []
        assert self.windows.names_for(date(2026, 12, 16), "expense") == []

    @pytest.mark.parametrize("kind", ["income", "transfer"])
    def test_only_expenses_are_stamped(self, kind):
        assert self.windows.names_for(date(2026, 12, 18), kind) == []


@pytest.fixture
def tag_service():
    svc = TripDefaultTagService(AsyncMock())
    svc._trip_repo = AsyncMock()
    svc._tag_repo = AsyncMock()
    svc._link_repo = AsyncMock()
    return svc


def _trip(**kw):
    base = dict(id=1, start_date=date(2026, 12, 17), end_date=date(2026, 12, 24), default_tag_names="Travel, Hotel")
    base.update(kw)
    return SimpleNamespace(**base)


class TestTripDefaultTagService:
    async def test_windows_skip_trips_without_default_tags(self, tag_service):
        tag_service._trip_repo.get_trips_in_window.return_value = [_trip(), _trip(id=2, default_tag_names=None)]
        windows = await tag_service.windows_for(date(2026, 12, 1), date(2026, 12, 31))
        assert windows.names_for(date(2026, 12, 18), "expense") == ["travel", "hotel"]

    async def test_names_for_one_day_queries_that_day(self, tag_service):
        tag_service._trip_repo.get_trips_in_window.return_value = [_trip()]
        assert await tag_service.names_for(date(2026, 12, 18), "expense") == ["travel", "hotel"]
        assert tag_service._trip_repo.get_trips_in_window.await_args.args == (date(2026, 12, 18), date(2026, 12, 18))

    async def test_apply_to_existing_tags_the_whole_trip_range(self, tag_service):
        tag_service._trip_repo.get_trip.return_value = _trip()
        tag_service._tag_repo.resolve_tags.return_value = [SimpleNamespace(id=5), SimpleNamespace(id=6)]
        tag_service._link_repo.tag_expenses_between.return_value = 7
        names, added = await tag_service.apply_to_existing(1)
        assert (names, added) == (["travel", "hotel"], 7)
        start, end, tag_ids = tag_service._link_repo.tag_expenses_between.await_args.args
        assert start == datetime(2026, 12, 17) and end == datetime(2026, 12, 25) and tag_ids == [5, 6]

    async def test_apply_without_default_tags_does_nothing(self, tag_service):
        tag_service._trip_repo.get_trip.return_value = _trip(default_tag_names="")
        assert await tag_service.apply_to_existing(1) == ([], 0)
        tag_service._link_repo.tag_expenses_between.assert_not_awaited()

    async def test_apply_unknown_trip(self, tag_service):
        tag_service._trip_repo.get_trip.return_value = None
        with pytest.raises(TravelNotFoundError):
            await tag_service.apply_to_existing(9)


class TestManualTransactionHook:
    async def test_expense_in_a_trip_picks_up_the_trip_tags(self):
        from app.features.finance.transactions.service import TransactionService

        svc = TransactionService.__new__(TransactionService)
        svc._repo = AsyncMock()
        svc._account_repo = AsyncMock()
        svc._fx = AsyncMock()
        svc._fx.convert_to_eur.return_value = None
        svc._trip_tags = AsyncMock()
        svc._trip_tags.names_for.return_value = ["Travel", "Hotel"]
        svc._repo.create.return_value = SimpleNamespace(
            id=1, account_id=1, date=datetime(2026, 12, 18), amount=Decimal("10"), currency="EUR", amount_eur=None,
            type="expense", category_id=None, description=None, bank_description=None, note=None, merchant="M",
            source=None, counterpart_account_id=None, counterpart_transaction_id=None, balance_after=None,
            import_batch_id=None, installment_plan_id=None, tags=[], created_at=datetime(2026, 12, 18),
        )
        await svc.create(TransactionCreate(
            account_id=1, date=datetime(2026, 12, 18), amount=Decimal("10"), currency="EUR", type="expense", tags=["travel", "Rome"],
        ))
        created = svc._repo.create.await_args.args[0]
        assert created.tags == ["travel", "Rome", "Hotel"]
        svc._trip_tags.names_for.assert_awaited_once_with(date(2026, 12, 18), "expense")


@pytest.fixture
def links():
    svc = TransactionLinkService(AsyncMock())
    for name in ("_repo", "_trip_repo", "_place_repo", "_leg_repo", "_stay_repo", "_visit_repo"):
        setattr(svc, name, AsyncMock())
    svc._repo.entity_exists.return_value = True
    return svc


def _txn(**kw):
    base = dict(id=9, date=datetime(2026, 12, 18), merchant="M", description=None, type="expense",
                amount=Decimal("10.00"), currency="EUR", amount_eur=Decimal("10.00"))
    base.update(kw)
    return SimpleNamespace(**base)


class TestTransactionLinkService:
    async def test_link_returns_the_updated_list_and_cost(self, links):
        links._repo.get_transaction.return_value = _txn()
        links._repo.get_linked.return_value = [_txn()]
        links._repo.get_entity_costs.return_value = {4: (Decimal("10.00"), 1, 0)}
        result = await links.link("legs", 4, 9)
        links._repo.link.assert_awaited_once_with("legs", 4, 9)
        assert result.cost.total_eur == Decimal("10.00") and result.cost.unconverted_count == 0
        assert result.transactions[0].id == 9

    async def test_transfers_are_refused(self, links):
        links._repo.get_transaction.return_value = _txn(type="transfer")
        with pytest.raises(TransferNotLinkableError):
            await links.link("stays", 4, 9)
        links._repo.link.assert_not_awaited()

    async def test_unknown_transaction_and_entity(self, links):
        links._repo.get_transaction.return_value = None
        with pytest.raises(TravelNotFoundError, match="Transaction"):
            await links.link("visits", 4, 9)
        links._repo.entity_exists.return_value = False
        with pytest.raises(TravelNotFoundError, match="Visit"):
            await links.get_linked("visits", 4)

    async def test_no_links_means_zero_cost_not_missing(self, links):
        links._repo.get_linked.return_value = []
        links._repo.get_entity_costs.return_value = {}
        result = await links.get_linked("legs", 4)
        assert result.cost.total_eur == Decimal("0.00") and result.cost.transaction_count == 0

    async def test_unconverted_transactions_are_reported(self, links):
        links._repo.get_linked.return_value = [_txn(amount_eur=None)]
        links._repo.get_entity_costs.return_value = {4: (Decimal("0.00"), 1, 1)}
        assert (await links.get_linked("legs", 4)).cost.unconverted_count == 1

    async def test_unlink(self, links):
        links._repo.unlink.return_value = False
        assert await links.unlink("legs", 4, 9) is False

    async def test_trip_costs_combine_total_kinds_and_items(self, links):
        links._trip_repo.get_trip.return_value = _trip()
        links._repo.get_tagged.return_value = []
        links._leg_repo.get_legs.return_value = [SimpleNamespace(id=1), SimpleNamespace(id=2)]
        links._stay_repo.get_stays.return_value = [SimpleNamespace(id=3)]
        links._visit_repo.get_trip_visits.return_value = []
        links._repo.get_trip_total.return_value = (Decimal("250.00"), 3, 1)
        links._repo.get_trip_costs_by_kind.return_value = {
            "flight": (Decimal("120.00"), 1, 0), "lodging": (Decimal("130.00"), 2, 1),
        }
        costs_by_kind = {"legs": {1: (Decimal("120.00"), 1, 0)}, "stays": {3: (Decimal("130.00"), 2, 1)}, "visits": {}}
        links._repo.get_entity_costs.side_effect = lambda kind, ids: costs_by_kind[kind]
        costs = await links.get_trip_costs(1)
        assert costs.total.total_eur == Decimal("250.00") and costs.total.unconverted_count == 1
        assert [k.kind for k in costs.by_kind] == ["flight", "lodging"]
        assert [e.id for e in costs.legs] == [1] and [e.id for e in costs.stays] == [3] and costs.visits == []

    async def test_tagged_charges_not_linked_are_a_separate_part_added_to_the_overall(self, links):
        links._trip_repo.get_trip.return_value = SimpleNamespace(
            start_date=date(2026, 12, 17), end_date=date(2026, 12, 29), default_tag_names="Travel")
        links._leg_repo.get_legs.return_value = []
        links._stay_repo.get_stays.return_value = []
        links._visit_repo.get_trip_visits.return_value = []
        links._repo.get_trip_total.return_value = (Decimal("100.00"), 1, 0)
        links._repo.get_trip_costs_by_kind.return_value = {}
        links._repo.get_entity_costs.return_value = {}
        links._repo.get_tagged.return_value = [
            (_txn(id=1, amount_eur=Decimal("-100.00")), True),
            (_txn(id=2, amount_eur=Decimal("-30.00")), False),
            (_txn(id=3, type="income", amount_eur=Decimal("5.00")), False),
            (_txn(id=4, amount_eur=None), False),
        ]
        costs = await links.get_trip_costs(1)
        assert costs.total.total_eur == Decimal("100.00")
        assert (costs.tagged.total_eur, costs.tagged.transaction_count, costs.tagged.unconverted_count) == (Decimal("25.00"), 3, 1)
        assert (costs.overall.total_eur, costs.overall.transaction_count, costs.overall.unconverted_count) == (Decimal("125.00"), 4, 1)

    async def test_trip_costs_unknown_trip(self, links):
        links._trip_repo.get_trip.return_value = None
        assert await links.get_trip_costs(9) is None

    async def test_place_costs(self, links):
        links._place_repo.get_place.return_value = SimpleNamespace(id=3)
        links._repo.get_place_total.return_value = (Decimal("80.00"), 2, 0)
        assert (await links.get_place_costs(3)).total.total_eur == Decimal("80.00")
        links._place_repo.get_place.return_value = None
        assert await links.get_place_costs(3) is None


class _Capture:
    def __init__(self):
        self.statements = []

    async def execute(self, stmt):
        self.statements.append(stmt)
        raise _Stop

    async def scalars(self, stmt):
        self.statements.append(stmt)
        raise _Stop


class _Stop(Exception):
    pass


async def _sql(call) -> str:
    session = _Capture()
    try:
        await call(TransactionLinkRepository(session))
    except _Stop:
        pass
    return str(session.statements[0].compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))


class TestUnlinkedService:
    async def test_uses_the_trip_dates_and_default_tags_to_leave_the_tagged_out(self, links):
        links._trip_repo.get_trip.return_value = SimpleNamespace(
            start_date=date(2026, 12, 17), end_date=date(2026, 12, 29), default_tag_names="Travel, Work")
        links._repo.get_unlinked.return_value = [_txn()]
        result = await links.get_unlinked(1)
        start, end, names = links._repo.get_unlinked.await_args.args
        assert (start, end, names) == (datetime(2026, 12, 17), datetime(2026, 12, 30), ["travel", "work"])
        assert [t.id for t in result] == [9]

    async def test_unknown_trip(self, links):
        links._trip_repo.get_trip.return_value = None
        assert await links.get_unlinked(9) is None


class TestTaggedService:
    async def test_lists_every_tagged_charge_with_its_link_state_and_counts_only_unlinked(self, links):
        links._trip_repo.get_trip.return_value = SimpleNamespace(
            start_date=date(2026, 12, 17), end_date=date(2026, 12, 29), default_tag_names="Travel, Work")
        links._repo.get_tagged.return_value = [
            (_txn(id=1, amount_eur=Decimal("40.00")), True), (_txn(id=2, amount_eur=Decimal("-30.00")), False),
        ]
        result = await links.get_tagged(1)
        names, start, end = links._repo.get_tagged.await_args.args
        assert names == ["travel", "work"] and (start, end) == (datetime(2026, 9, 18), datetime(2027, 1, 29))
        assert [(t.id, t.linked) for t in result.transactions] == [(1, True), (2, False)]
        assert result.cost.total_eur == Decimal("30.00") and result.cost.transaction_count == 1

    async def test_unknown_trip(self, links):
        links._trip_repo.get_trip.return_value = None
        assert await links.get_tagged(9) is None


class TestCostSql:
    async def test_tagged_query_matches_tags_case_insensitively_and_flags_linked_ones(self):
        sql = await _sql(lambda r: r.get_tagged(["Travel"], datetime(2026, 9, 18), datetime(2027, 1, 30)))
        assert "lower(finance.tags.name) IN ('travel')" in sql and "type IN ('expense', 'income')" in sql
        assert "travel.legs_transactions" in sql and "travel.visits_transactions" in sql and "'transfer'" not in sql

    async def test_tagged_query_requires_every_default_tag_not_just_one(self):
        sql = await _sql(lambda r: r.get_tagged(["Travel", "Christmas", "travel"], datetime(2026, 9, 18), datetime(2027, 1, 30)))
        assert "lower(finance.tags.name) IN ('christmas', 'travel')" in sql
        assert "GROUP BY finance.transactions_tags.transaction_id" in sql
        assert "count(distinct(lower(finance.tags.name))) = 2" in sql

    async def test_unlinked_query_keeps_charges_that_carry_only_some_of_the_tags(self):
        sql = await _sql(lambda r: r.get_unlinked(datetime(2026, 12, 17), datetime(2026, 12, 30), ["Travel", "Christmas"]))
        assert "count(distinct(lower(finance.tags.name))) = 2" in sql

    async def test_tagged_query_without_tags_is_empty_without_touching_the_db(self):
        session = _Capture()
        assert await TransactionLinkRepository(session).get_tagged([], datetime(2026, 9, 18), datetime(2027, 1, 30)) == []
        assert session.statements == []

    async def test_trip_total_counts_each_transaction_once(self):
        sql = await _sql(lambda r: r.get_trip_total(1))
        assert "UNION" in sql and "travel.legs_transactions" in sql and "travel.stays_transactions" in sql
        assert "travel.visits_transactions" in sql and "WHERE finance.transactions.id IN" in sql

    async def test_refunds_count_down(self):
        sql = await _sql(lambda r: r.get_trip_total(1))
        assert "CASE WHEN (finance.transactions.type = 'income') THEN -abs(finance.transactions.amount_eur)" in sql

    async def test_unconverted_are_counted_separately(self):
        assert "FILTER (WHERE finance.transactions.amount_eur IS NULL)" in await _sql(lambda r: r.get_trip_total(1))

    async def test_by_kind_groups_legs_stays_and_visits(self):
        sql = await _sql(lambda r: r.get_trip_costs_by_kind(1))
        assert "'lodging'" in sql and "travel.legs.mode" in sql and "travel.places.kind" in sql and "GROUP BY" in sql

    async def test_place_total_covers_visits_and_stays(self):
        sql = await _sql(lambda r: r.get_place_total(3))
        assert "travel.visits.place_id = 3" in sql and "travel.stays.place_id = 3" in sql

    async def test_entity_costs_group_by_the_link_column(self):
        assert "GROUP BY travel.legs_transactions.leg_id" in await _sql(lambda r: r.get_entity_costs("legs", [1, 2]))

    async def test_unlinked_query_keeps_untagged_unlinked_trip_expenses_only(self):
        sql = await _sql(lambda r: r.get_unlinked(datetime(2026, 12, 17), datetime(2026, 12, 30), ["Travel"]))
        assert "travel.visits_transactions" in sql and "UNION" in sql
        assert "NOT IN (SELECT finance.transactions_tags.transaction_id" in sql
        assert "lower(finance.tags.name) IN ('travel')" in sql
        assert "type = 'expense'" in sql and "'income'" not in sql and "'transfer'" not in sql
        assert "finance.transactions.date >= '2026-12-17" in sql and "finance.transactions.date < '2026-12-30" in sql

    async def test_unlinked_query_without_tags_only_matches_dated_expenses(self):
        sql = await _sql(lambda r: r.get_unlinked(datetime(2026, 12, 17), datetime(2026, 12, 30), []))
        assert "finance.tags" not in sql

    async def test_tagging_inserts_missing_rows_only(self):
        sql = await _sql(lambda r: r.tag_expenses_between(datetime(2026, 12, 17), datetime(2026, 12, 25), [5]))
        assert "ON CONFLICT DO NOTHING" in sql and "finance.transactions_tags" in sql
        assert "finance.transactions.type = 'expense'" in sql and "finance.transactions.date <" in sql


class TestCalendarImport:
    @pytest.fixture
    def calendar(self):
        svc = CalendarImportService(AsyncMock())
        svc._events = AsyncMock()
        svc._trip_repo = AsyncMock()
        svc._leg_repo = AsyncMock()
        svc._stay_repo = AsyncMock()
        svc._leg_repo.get_imported_event_ids.return_value = {}
        svc._stay_repo.get_imported_event_ids.return_value = {}
        return svc

    def _event(self, id, title="Flight XX 12", tz="Europe/Stockholm", rule=None):
        return SimpleNamespace(
            id=id, title=title, location="Airport", description=None, all_day=False, timezone=tz,
            start_datetime=datetime(2026, 12, 17, 6, 0), end_datetime=datetime(2026, 12, 17, 9, 0), recurrence_rule=rule,
        )

    async def test_unknown_trip(self, calendar):
        calendar._trip_repo.get_trip.return_value = None
        assert await calendar.get_candidates(9) is None

    async def test_asks_the_local_copy_for_the_trip_range(self, calendar):
        calendar._trip_repo.get_trip.return_value = _trip()
        calendar._events.get_events.return_value = []
        await calendar.get_candidates(1)
        filters = calendar._events.get_events.await_args.args[0]
        assert filters.start_from == datetime(2026, 12, 17) and filters.start_to == datetime(2026, 12, 25)

    async def test_times_are_shown_in_the_event_zone(self, calendar):
        calendar._trip_repo.get_trip.return_value = _trip()
        # 06:00 in the portal zone (Lisbon, UTC+0 in winter) is 07:00 in Stockholm
        calendar._events.get_events.return_value = [self._event(1)]
        [candidate] = await calendar.get_candidates(1)
        assert candidate.start_local == datetime(2026, 12, 17, 7, 0) and candidate.timezone == "Europe/Stockholm"

    async def test_recurring_events_are_skipped(self, calendar):
        calendar._trip_repo.get_trip.return_value = _trip()
        calendar._events.get_events.return_value = [self._event(1, rule="FREQ=WEEKLY"), self._event(2)]
        assert [c.event_id for c in await calendar.get_candidates(1)] == [2]

    async def test_already_imported_events_are_marked(self, calendar):
        calendar._trip_repo.get_trip.return_value = _trip()
        calendar._events.get_events.return_value = [self._event(1), self._event(2), self._event(3)]
        calendar._leg_repo.get_imported_event_ids.return_value = {1: 40}
        calendar._stay_repo.get_imported_event_ids.return_value = {2: 50}
        candidates = await calendar.get_candidates(1)
        assert [(c.imported_as, c.imported_id) for c in candidates] == [("leg", 40), ("stay", 50), (None, None)]


class TestImportedEventsAreImportedOnce:
    def _leg(self):
        return LegCreate(
            trip_id=1, mode="flight", origin="A", destination="B", departs_at=datetime(2026, 12, 17, 6),
            arrives_at=datetime(2026, 12, 17, 10), departs_tz="UTC", arrives_tz="UTC", calendar_event_id=77,
        )

    async def test_leg_from_an_unknown_event(self):
        svc = LegService(AsyncMock())
        svc._repo, svc._trip_repo, svc._event_links = AsyncMock(), AsyncMock(), AsyncMock()
        svc._event_links.ensure_free.side_effect = TravelNotFoundError("Calendar event 77 not found")
        with pytest.raises(TravelNotFoundError, match="Calendar event"):
            await svc.create_leg(self._leg())

    async def test_leg_from_an_event_already_imported(self):
        svc = LegService(AsyncMock())
        svc._repo, svc._trip_repo, svc._event_links = AsyncMock(), AsyncMock(), AsyncMock()
        svc._event_links.ensure_free.side_effect = TravelConflictError("taken")
        with pytest.raises(TravelConflictError):
            await svc.create_leg(self._leg())
        svc._repo.create_leg.assert_not_awaited()

    async def test_stay_from_an_event_already_imported(self):
        svc = StayService(AsyncMock())
        svc._repo, svc._trip_repo, svc._place_repo, svc._event_links = AsyncMock(), AsyncMock(), AsyncMock(), AsyncMock()
        svc._event_links.ensure_free.side_effect = TravelConflictError("taken")
        data = StayCreate(place_id=3, trip_id=1, check_in_at=datetime(2026, 12, 18, 15), check_out_at=datetime(2026, 12, 19, 11),
                          timezone="UTC", calendar_event_id=77)
        with pytest.raises(TravelConflictError):
            await svc.create_stay(data)
        svc._repo.create_stay.assert_not_awaited()

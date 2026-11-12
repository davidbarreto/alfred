from datetime import date, datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.features.finance.recurring_transactions.service import next_occurrence
from app.features.travel.trips.while_away import birthdays_between, occurrences_between
from app.features.travel.trips.while_away_service import WhileAwayService


class TestBirthdaysBetween:
    def test_inside_the_range(self):
        assert birthdays_between(date(1990, 12, 20), date(2026, 12, 17), date(2026, 12, 29)) == [date(2026, 12, 20)]

    def test_outside_the_range(self):
        assert birthdays_between(date(1990, 1, 5), date(2026, 12, 17), date(2026, 12, 29)) == []

    def test_a_trip_over_new_year_catches_both_years(self):
        assert birthdays_between(date(1990, 1, 2), date(2026, 12, 28), date(2027, 1, 3)) == [date(2027, 1, 2)]

    def test_leap_day_birthdays_fall_on_the_first_of_march(self):
        assert birthdays_between(date(2000, 2, 29), date(2027, 2, 25), date(2027, 3, 3)) == [date(2027, 3, 1)]


class TestOccurrencesBetween:
    def test_monthly_charge_from_its_last_run(self):
        found = occurrences_between("FREQ=MONTHLY", date(2026, 11, 20), date(2026, 12, 17), date(2027, 1, 25), next_occurrence, date(2026, 12, 10))
        assert found == [date(2026, 12, 20), date(2027, 1, 20)]

    def test_weekly_charge_inside_a_short_trip(self):
        found = occurrences_between("FREQ=WEEKLY", date(2026, 12, 14), date(2026, 12, 17), date(2026, 12, 29), next_occurrence, date(2026, 12, 10))
        assert found == [date(2026, 12, 21), date(2026, 12, 28)]

    def test_a_rule_that_never_ran_starts_at_the_trip(self):
        assert occurrences_between("FREQ=YEARLY", None, date(2026, 12, 17), date(2026, 12, 29), next_occurrence, date(2026, 12, 10)) == []

    def test_a_rule_that_never_ran_starts_today_when_today_is_inside_the_trip(self):
        found = occurrences_between("FREQ=WEEKLY", None, date(2026, 12, 8), date(2026, 12, 16), next_occurrence, date(2026, 12, 10))
        assert found == [date(2026, 12, 10)]

    def test_an_exhausted_rule_yields_nothing(self):
        rule = "FREQ=MONTHLY;UNTIL=20261001T000000Z"
        assert occurrences_between(rule, date(2026, 9, 20), date(2026, 12, 17), date(2026, 12, 29), next_occurrence, date(2026, 12, 10)) == []

    def test_unknown_frequency_yields_nothing(self):
        assert occurrences_between("FREQ=HOURLY", date(2026, 9, 20), date(2026, 12, 17), date(2026, 12, 29), next_occurrence, date(2026, 12, 10)) == []


@pytest.fixture
def service():
    svc = WhileAwayService(AsyncMock())
    svc._trips, svc._contacts, svc._tasks, svc._recurring = AsyncMock(), AsyncMock(), AsyncMock(), AsyncMock()
    svc._trips.get_trip.return_value = SimpleNamespace(start_date=date(2026, 12, 17), end_date=date(2026, 12, 29))
    return svc


class TestService:
    async def test_collects_the_three_kinds_and_skips_income(self, service):
        service._contacts.get_all_with_birthday.return_value = [SimpleNamespace(id=1, name="Some Person", birthday=date(1990, 12, 20))]
        service._tasks.get_tasks.return_value = [SimpleNamespace(id=4, title="Renew insurance", deadline=datetime(2026, 12, 22, 23, 59))]
        service._recurring.list_active.return_value = [
            SimpleNamespace(id=7, merchant="Streaming", amount=Decimal("9.99"), currency="EUR", type="expense",
                            recurrence_rule="FREQ=MONTHLY", last_occurrence_date=date(2026, 11, 25)),
            SimpleNamespace(id=8, merchant="Salary", amount=Decimal("1000"), currency="EUR", type="income",
                            recurrence_rule="FREQ=MONTHLY", last_occurrence_date=date(2026, 11, 25)),
        ]
        result = await service.get_while_away(1)
        assert [(b.name, b.date) for b in result.birthdays] == [("Some Person", date(2026, 12, 20))]
        assert [(t.title, t.due) for t in result.tasks] == [("Renew insurance", date(2026, 12, 22))]
        assert [(c.merchant, c.date) for c in result.charges] == [("Streaming", date(2026, 12, 25))]
        filters = service._tasks.get_tasks.await_args.args[0]
        assert filters.status == "ACTIVE" and filters.include_recurring is False

    async def test_unknown_trip(self, service):
        service._trips.get_trip.return_value = None
        assert await service.get_while_away(9) is None

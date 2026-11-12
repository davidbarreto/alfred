from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.features.travel.errors import TravelConflictError, TravelNotFoundError
from app.features.travel.event_links import EventLinkChecker
from app.features.travel.legs.schemas import LegUpdate
from app.features.travel.legs.service import LegService
from app.features.travel.stays.schemas import StayUpdate
from app.features.travel.stays.service import StayService


@pytest.fixture
def checker():
    c = EventLinkChecker(AsyncMock())
    c._events, c._legs, c._stays, c._visits = AsyncMock(), AsyncMock(), AsyncMock(), AsyncMock()
    for repo, name in ((c._legs, "get_leg_by_calendar_event"), (c._stays, "get_stay_by_calendar_event"),
                       (c._visits, "get_visit_by_calendar_event")):
        getattr(repo, name).return_value = None
    c._events.get_event.return_value = object()
    return c


class TestEnsureFree:
    async def test_a_free_event_passes(self, checker):
        await checker.ensure_free(5)

    async def test_unknown_event_is_not_found(self, checker):
        checker._events.get_event.return_value = None
        with pytest.raises(TravelNotFoundError):
            await checker.ensure_free(5)

    @pytest.mark.parametrize("repo,method,kind", [
        ("_legs", "get_leg_by_calendar_event", "leg"),
        ("_stays", "get_stay_by_calendar_event", "stay"),
        ("_visits", "get_visit_by_calendar_event", "visit"),
    ])
    async def test_an_event_held_by_any_kind_is_a_conflict(self, checker, repo, method, kind):
        getattr(getattr(checker, repo), method).return_value = SimpleNamespace(id=1)
        with pytest.raises(TravelConflictError, match=kind):
            await checker.ensure_free(5)

    async def test_the_item_being_edited_may_keep_its_own_event(self, checker):
        checker._visits.get_visit_by_calendar_event.return_value = SimpleNamespace(id=11)
        await checker.ensure_free(5, "visit", 11)
        with pytest.raises(TravelConflictError):
            await checker.ensure_free(5, "visit", 12)
        with pytest.raises(TravelConflictError):
            await checker.ensure_free(5, "leg", 11)


class TestUpdatingLinks:
    async def test_a_leg_can_be_linked_and_unlinked_on_update(self):
        svc = LegService(AsyncMock())
        svc._repo, svc._event_links = AsyncMock(), AsyncMock()
        leg = SimpleNamespace(id=1, departs_tz="UTC", arrives_tz="UTC", departs_at=datetime(2026, 12, 17, 6),
                              arrives_at=datetime(2026, 12, 17, 9))
        svc._repo.get_leg.return_value = leg
        svc._repo.update_leg.side_effect = RuntimeError("stop")
        for body, checked in ((LegUpdate(calendar_event_id=7), True), (LegUpdate(calendar_event_id=None), False)):
            svc._event_links.reset_mock()
            with pytest.raises(RuntimeError):
                await svc.update_leg(1, body)
            assert svc._event_links.ensure_free.await_count == (1 if checked else 0)
        assert svc._repo.update_leg.await_args.args[1] == {"calendar_event_id": None}

    async def test_a_stay_update_checks_the_event_against_all_items(self):
        svc = StayService(AsyncMock())
        svc._repo, svc._trip_repo, svc._place_repo, svc._event_links = AsyncMock(), AsyncMock(), AsyncMock(), AsyncMock()
        svc._repo.get_stay.return_value = SimpleNamespace(id=4, timezone="UTC", check_in_at=datetime(2026, 12, 18),
                                                          check_out_at=datetime(2026, 12, 20))
        svc._event_links.ensure_free.side_effect = TravelConflictError("taken")
        with pytest.raises(TravelConflictError):
            await svc.update_stay(4, StayUpdate(calendar_event_id=7))
        svc._event_links.ensure_free.assert_awaited_once_with(7, "stay", 4)
        svc._repo.update_stay.assert_not_awaited()

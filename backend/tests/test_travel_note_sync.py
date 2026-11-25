"""Creating, editing and deleting a trip, leg, stay, visit or place keeps its notes embedding in step."""
from datetime import date, datetime, time, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from travel_city_helpers import city_ref
from app.features.travel.legs.schemas import LegCreate, LegUpdate
from app.features.travel.legs.service import LegService
from app.features.travel.places.hooks import TravelPlaceHooks
from app.features.travel.stays.schemas import StayCreate, StayUpdate
from app.features.travel.stays.service import StayService
from app.features.travel.tags.tables import TravelTag
from app.features.travel.trips.schemas import TripCreate, TripUpdate
from app.features.travel.trips.service import TripService
from app.features.travel.visits.schemas import VisitCreate, VisitUpdate
from app.features.travel.visits.service import VisitService

NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


@pytest.fixture
def embeddings():
    service = MagicMock()
    service.delete_by_source = AsyncMock()
    return service


def _embedded(embeddings):
    data = embeddings.embed_background.call_args.args[0]
    return data.source_type, data.source_id, data.content


def _place(**kw):
    base = dict(id=3, kind="restaurant", name="Cafe Example", city=city_ref("Lisbon"), maps_url=None, latitude=None, longitude=None,
                address=None, notes="Book the terrace", tags=[], created_at=NOW, updated_at=NOW)
    base.update(kw)
    return SimpleNamespace(**base)


def _trip(**kw):
    base = dict(id=1, name="Example trip", start_date=date(2031, 12, 17), end_date=date(2031, 12, 24), travelers=None,
                preferences=None, checklist_note_id=None, notes="Overview", default_tag_names=None, tags=[],
                created_at=NOW, updated_at=NOW)
    base.update(kw)
    return SimpleNamespace(**base)


def _leg(**kw):
    base = dict(id=2, trip_id=1, mode="flight", origin="Alpha", destination="Beta", origin_code=None, destination_code=None,
                departs_at=datetime(2031, 12, 17, 6, tzinfo=timezone.utc), arrives_at=datetime(2031, 12, 17, 9, tzinfo=timezone.utc),
                departs_tz="UTC", arrives_tz="UTC", carrier=None, number=None, booking_ref=None, booking_url=None, seat=None,
                notes="Terminal 2", created_at=NOW, updated_at=NOW)
    base.update(kw)
    return SimpleNamespace(**base)


def _stay(**kw):
    base = dict(id=7, trip_id=1, place_id=3, place=_place(name="Hotel Example", kind="hotel"),
                check_in_at=datetime(2031, 12, 18, 14, tzinfo=timezone.utc), check_out_at=datetime(2031, 12, 20, 10, tzinfo=timezone.utc),
                timezone="UTC", booking_ref=None, booking_url=None, notes="Quiet room", grade=None, created_at=NOW, updated_at=NOW)
    base.update(kw)
    return SimpleNamespace(**base)


def _visit(**kw):
    base = dict(id=11, place_id=3, place=_place(), trip_id=1, trip_name="Example trip", status="visited",
                visit_date=date(2031, 12, 18), visit_time=time(20, 0), notes="Great pasta", grade=None, calendar_event_id=None, created_at=NOW, updated_at=NOW)
    base.update(kw)
    return SimpleNamespace(**base)


class TestTrips:
    @pytest.fixture
    def svc(self, embeddings):
        svc = TripService(AsyncMock(), embeddings)
        svc._repo, svc._tag_repo, svc._leg_repo = AsyncMock(), AsyncMock(), AsyncMock()
        svc._web_link_repo = AsyncMock()
        svc._web_link_repo.get_link_ids.return_value = []
        svc._tag_repo.get_or_create_tags.return_value = [TravelTag(name="x")][:0]
        return svc

    async def test_create_indexes_the_notes(self, svc, embeddings):
        svc._repo.create_trip.return_value = _trip()
        await svc.create_trip(TripCreate(name="Example trip", start_date=date(2031, 12, 17), end_date=date(2031, 12, 24), notes="Overview"))
        assert _embedded(embeddings) == ("trip_note", 1, "Trip Example trip: Overview")

    async def test_clearing_the_notes_drops_the_embedding(self, svc, embeddings):
        svc._repo.get_trip.return_value = _trip()
        svc._repo.update_trip.return_value = _trip(notes=None)
        await svc.update_trip(1, TripUpdate.model_validate({"notes": None}))
        embeddings.delete_by_source.assert_awaited_once_with("trip_note", 1)

    async def test_an_unrelated_edit_leaves_the_index_alone(self, svc, embeddings):
        svc._repo.get_trip.return_value = _trip()
        svc._repo.update_trip.return_value = _trip(travelers="Test travelers")
        await svc.update_trip(1, TripUpdate(travelers="Test travelers"))
        embeddings.embed_background.assert_not_called()
        embeddings.delete_by_source.assert_not_awaited()

    async def test_deleting_a_trip_drops_its_note_and_its_legs_notes(self, svc, embeddings):
        svc._leg_repo.get_legs.return_value = [SimpleNamespace(id=2), SimpleNamespace(id=5)]
        svc._repo.delete_trip.return_value = True
        await svc.delete_trip(1)
        removed = {c.args for c in embeddings.delete_by_source.await_args_list}
        assert removed == {("trip_note", 1), ("leg_note", 2), ("leg_note", 5)}

    async def test_deleting_a_trip_drops_its_links_notes(self, svc, embeddings):
        svc._leg_repo.get_legs.return_value = []
        svc._web_link_repo.get_link_ids.return_value = [8, 9]
        svc._repo.delete_trip.return_value = True
        await svc.delete_trip(1)
        removed = {c.args for c in embeddings.delete_by_source.await_args_list}
        assert removed == {("trip_note", 1), ("web_link_note", 8), ("web_link_note", 9)}

    async def test_deleting_a_missing_trip_removes_nothing(self, svc, embeddings):
        svc._leg_repo.get_legs.return_value = []
        svc._repo.delete_trip.return_value = False
        await svc.delete_trip(1)
        embeddings.delete_by_source.assert_not_awaited()


class TestLegs:
    @pytest.fixture
    def svc(self, embeddings):
        svc = LegService(AsyncMock(), embeddings)
        svc._repo, svc._trip_repo, svc._event_links = AsyncMock(), AsyncMock(), AsyncMock()
        svc._city_repo = AsyncMock()
        svc._city_repo.find_unique_city_id.return_value = None
        return svc

    async def test_create_update_delete(self, svc, embeddings):
        svc._repo.create_leg.return_value = _leg()
        await svc.create_leg(LegCreate(
            trip_id=1, mode="flight", origin="Alpha", destination="Beta", departs_at=datetime(2031, 12, 17, 6),
            arrives_at=datetime(2031, 12, 17, 9), departs_tz="UTC", arrives_tz="UTC", notes="Terminal 2",
        ))
        assert _embedded(embeddings) == ("leg_note", 2, "Alpha to Beta (flight): Terminal 2")
        embeddings.embed_background.reset_mock()

        svc._repo.get_leg.return_value = _leg()
        svc._repo.update_leg.return_value = _leg(notes=None)
        await svc.update_leg(2, LegUpdate.model_validate({"notes": None}))
        embeddings.delete_by_source.assert_awaited_with("leg_note", 2)

        svc._repo.update_leg.return_value = _leg()
        await svc.update_leg(2, LegUpdate(seat="1A"))
        embeddings.embed_background.assert_not_called()

        await svc.delete_leg(2)
        assert embeddings.delete_by_source.await_args.args == ("leg_note", 2)


class TestStays:
    @pytest.fixture
    def svc(self, embeddings):
        svc = StayService(AsyncMock(), embeddings)
        svc._repo, svc._trip_repo, svc._place_repo, svc._event_links = AsyncMock(), AsyncMock(), AsyncMock(), AsyncMock()
        return svc

    async def test_create_update_delete(self, svc, embeddings):
        svc._repo.create_stay.return_value = _stay()
        await svc.create_stay(StayCreate(
            place_id=3, trip_id=1, check_in_at=datetime(2031, 12, 18, 14), check_out_at=datetime(2031, 12, 20, 10),
            timezone="UTC", notes="Quiet room",
        ))
        assert _embedded(embeddings) == ("stay_note", 7, "Stay at Hotel Example: Quiet room")

        svc._repo.get_stay.return_value = _stay()
        svc._repo.update_stay.return_value = _stay(notes="")
        await svc.update_stay(7, StayUpdate(notes=""))
        embeddings.delete_by_source.assert_awaited_with("stay_note", 7)

        await svc.delete_stay(7)
        assert embeddings.delete_by_source.await_args.args == ("stay_note", 7)


class TestVisits:
    @pytest.fixture
    def svc(self, embeddings):
        svc = VisitService(AsyncMock(), embeddings)
        svc._repo, svc._trip_repo, svc._place_repo = AsyncMock(), AsyncMock(), AsyncMock()
        return svc

    async def test_create_update_delete(self, svc, embeddings):
        svc._repo.create_visit.return_value = _visit()
        await svc.create_visit(VisitCreate(place_id=3, status="visited", notes="Great pasta"))
        assert _embedded(embeddings) == ("visit_note", 11, "Visit to Cafe Example: Great pasta")

        svc._repo.get_visit.return_value = _visit()
        svc._repo.update_visit.return_value = _visit(notes=None)
        await svc.update_visit(11, VisitUpdate.model_validate({"notes": None}))
        embeddings.delete_by_source.assert_awaited_with("visit_note", 11)

        await svc.delete_visit(11)
        assert embeddings.delete_by_source.await_args.args == ("visit_note", 11)


class TestPlaces:
    """Place notes are indexed by travel's place hooks, whichever API saved or deleted the place."""

    @pytest.fixture
    def hooks(self, embeddings):
        hooks = TravelPlaceHooks(AsyncMock(), embeddings)
        hooks._links = AsyncMock()
        hooks._links.get_link_ids.return_value = []
        return hooks

    async def test_a_saved_place_indexes_its_notes(self, hooks, embeddings):
        await hooks.place_saved(_place(notes="Book the terrace"))
        assert _embedded(embeddings) == ("place_note", 3, "Cafe Example: Book the terrace")

    async def test_cleared_notes_drop_the_embedding(self, hooks, embeddings):
        await hooks.place_saved(_place(notes=" "))
        assert embeddings.delete_by_source.await_args.args == ("place_note", 3)

    async def test_deleting_a_place_drops_its_notes_and_its_links_notes_after_the_commit(self, hooks, embeddings):
        hooks._links.get_link_ids.return_value = [4]

        after = await hooks.before_place_delete(3)
        embeddings.delete_by_source.assert_not_awaited()
        await after()

        removed = {c.args for c in embeddings.delete_by_source.await_args_list}
        assert removed == {("place_note", 3), ("web_link_note", 4)}

    async def test_visits_and_stays_hold_the_place(self, hooks):
        hooks._count = AsyncMock(side_effect=[2, 1])
        assert await hooks.place_in_use(_place()) == "it has 2 visit(s) and 1 stay(s)"
        hooks._count = AsyncMock(return_value=0)
        assert await hooks.place_in_use(_place()) is None


from datetime import date, datetime, time, timezone

from app.features.travel.visits.note_log import append_note, pick_note_visit
from app.features.travel.visits.schemas import VisitPlace, VisitRead

NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _visit(id, day, at=None, status="planned", notes=None):
    place = VisitPlace(id=id, kind="museum", name=f"Museum {id}", city="Beta", maps_url=None, lat=None, lng=None)
    return VisitRead(
        id=id, place_id=id, place=place, trip_id=1, trip_name="T", status=status,
        visit_date=date(2026, 12, day) if day else None, visit_time=at, notes=notes, grade=None,
        created_at=NOW, updated_at=NOW,
    )


LOCAL_NOW = datetime(2026, 12, 18, 15, 0)


class TestPickNoteVisit:
    def test_the_latest_visit_that_has_already_started(self):
        visits = [_visit(1, 17, time(10)), _visit(2, 18, time(9)), _visit(3, 18, time(14, 30)), _visit(4, 18, time(18))]
        assert pick_note_visit(visits, LOCAL_NOW).id == 3

    def test_nothing_started_yet_gives_none(self):
        assert pick_note_visit([_visit(1, 18, time(18)), _visit(2, 19, time(9))], LOCAL_NOW) is None

    def test_an_untimed_visit_counts_from_the_start_of_its_day(self):
        assert pick_note_visit([_visit(1, 18, None)], LOCAL_NOW).id == 1

    def test_undated_and_missed_visits_are_ignored(self):
        assert pick_note_visit([_visit(1, None), _visit(2, 18, time(9), status="missed")], LOCAL_NOW) is None


class TestAppendNote:
    def test_first_note_is_just_the_stamped_line(self):
        assert append_note(None, LOCAL_NOW, " great view ") == "[2026-12-18 15:00] great view"

    def test_later_notes_go_on_a_new_line_after_the_existing_ones(self):
        assert append_note("Booked a table\n", LOCAL_NOW, "late") == "Booked a table\n[2026-12-18 15:00] late"

    def test_blank_existing_notes_are_treated_as_empty(self):
        assert append_note("  ", LOCAL_NOW, "x") == "[2026-12-18 15:00] x"

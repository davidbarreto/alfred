import pytest
from datetime import datetime
from app.features.organizer.tasks.schemas import (
    TaskCreate,
    TaskUpdate,
    TaskRead,
    TaskFilters,
)


class TestTaskCreate:
    def test_required_title(self):
        task = TaskCreate(title="Do the thing")
        assert task.title == "Do the thing"

    def test_defaults(self):
        task = TaskCreate(title="Test")
        assert task.status == "TODO"
        assert task.priority == "LOW"
        assert task.urgency == "NORMAL"
        assert task.tags == []
        assert task.deadline is None
        assert task.recurrence_rule is None

    def test_with_all_fields(self):
        task = TaskCreate(
            title="Full task",
            status="DOING",
            priority="HIGH",
            urgency="URGENT",
            deadline=datetime(2024, 6, 1),
            tags=["work", "urgent"],
            recurrence_rule="weekly",
        )
        assert task.status == "DOING"
        assert task.priority == "HIGH"
        assert task.urgency == "URGENT"
        assert task.tags == ["work", "urgent"]

    def test_cancelled_status_valid(self):
        task = TaskCreate(title="Dropped", status="CANCELLED")
        assert task.status == "CANCELLED"


class TestTaskUpdate:
    def test_all_fields_optional(self):
        update = TaskUpdate()
        assert update.title is None
        assert update.status is None
        assert update.priority is None
        assert update.urgency is None
        assert update.deadline is None
        assert update.tags is None
        assert update.recurrence_rule is None

    def test_partial_update(self):
        update = TaskUpdate(status="DONE")
        assert update.status == "DONE"
        assert update.title is None

    def test_model_dump_excludes_unset(self):
        update = TaskUpdate(status="DONE")
        dumped = update.model_dump(exclude_unset=True)
        assert "status" in dumped
        assert "title" not in dumped


class TestTaskRead:
    def test_from_dict(self):
        task = TaskRead(
            id=1,
            title="Test",
            status="TODO",
            priority="LOW",
            urgency="NORMAL",
            tags=[],
            created_at=datetime(2024, 6, 1),
        )
        assert task.id == 1

    def test_coerce_tags_from_strings(self):
        task = TaskRead(
            id=1, title="T", status="TODO", priority="LOW", urgency="NORMAL",
            tags=["work", "personal"], created_at=datetime(2024, 6, 1),
        )
        assert task.tags == ["work", "personal"]

    def test_coerce_tags_from_orm_objects(self):
        class FakeTag:
            name = "work"

        task = TaskRead(
            id=2, title="T", status="TODO", priority="LOW", urgency="NORMAL",
            tags=[FakeTag()], created_at=datetime(2024, 6, 1),
        )
        assert task.tags == ["work"]

    def test_coerce_tags_mixed(self):
        class FakeTag:
            def __init__(self, name):
                self.name = name

        task = TaskRead(
            id=3, title="T", status="TODO", priority="LOW", urgency="NORMAL",
            tags=[FakeTag("work"), "personal"], created_at=datetime(2024, 6, 1),
        )
        assert task.tags == ["work", "personal"]

    def test_from_attributes_enabled(self):
        assert TaskRead.model_config.get("from_attributes") is True

    def test_is_done_in_cycle_defaults_false(self):
        task = TaskRead(
            id=1, title="T", status="TODO", priority="LOW", urgency="NORMAL",
            tags=[], created_at=datetime(2024, 6, 1),
        )
        assert task.is_done_in_cycle is False


class TestTaskFilters:
    def test_defaults(self):
        filters = TaskFilters()
        assert filters.limit == 100
        assert filters.status == "ALL"
        assert filters.priority == "ALL"
        assert filters.urgency == "ALL"
        assert filters.tags is None
        assert filters.deadline_from is None
        assert filters.deadline_to is None
        assert filters.due_today is False

    def test_custom_values(self):
        filters = TaskFilters(
            limit=10,
            status="TODO",
            priority="HIGH",
            urgency="URGENT",
            tags=["work"],
            deadline_from=datetime(2024, 1, 1),
            deadline_to=datetime(2024, 12, 31),
        )
        assert filters.limit == 10
        assert filters.status == "TODO"
        assert filters.priority == "HIGH"
        assert filters.tags == ["work"]


class TestTaskCompletionUpdate:
    def test_accepts_a_single_field(self):
        from datetime import date
        from app.features.organizer.tasks.schemas import TaskCompletionUpdate
        assert TaskCompletionUpdate(completed_on=date(2026, 9, 1)).occurrence_date is None

    def test_rejects_empty_body(self):
        import pytest
        from pydantic import ValidationError
        from app.features.organizer.tasks.schemas import TaskCompletionUpdate
        with pytest.raises(ValidationError):
            TaskCompletionUpdate()

    def test_rejects_explicit_nulls(self):
        import pytest
        from pydantic import ValidationError
        from app.features.organizer.tasks.schemas import TaskCompletionUpdate
        with pytest.raises(ValidationError):
            TaskCompletionUpdate(occurrence_date=None, completed_on=None)


class TestTaskReadSerializesWithOffset:
    """Task datetimes are stored as naive local time; JSON output states the offset (as
    day_plan and events do) so a client never has to guess the zone."""

    def _read(self, **overrides) -> TaskRead:
        data = dict(id=1, title="Pay rent", created_at=datetime(2026, 10, 1, 9, 30))
        data.update(overrides)
        return TaskRead(**data)

    def test_winter_datetimes_carry_the_lisbon_offset(self):
        task = self._read(
            deadline=datetime(2026, 11, 15), available_from=datetime(2026, 11, 1, 8, 0),
            completed_at=datetime(2026, 11, 16, 10, 0),
        )

        dumped = task.model_dump(mode="json")

        assert dumped["deadline"] == "2026-11-15T00:00:00+00:00"
        assert dumped["available_from"] == "2026-11-01T08:00:00+00:00"
        assert dumped["completed_at"] == "2026-11-16T10:00:00+00:00"

    def test_summer_datetimes_follow_dst(self):
        assert self._read(deadline=datetime(2026, 7, 15, 12, 0)).model_dump(mode="json")["deadline"] == (
            "2026-07-15T12:00:00+01:00"
        )

    def test_created_at_carries_an_offset(self):
        assert self._read().model_dump(mode="json")["created_at"] == "2026-10-01T09:30:00+01:00"

    def test_missing_datetimes_stay_null(self):
        dumped = self._read().model_dump(mode="json")

        assert dumped["deadline"] is None
        assert dumped["available_from"] is None
        assert dumped["completed_at"] is None

    def test_python_values_stay_naive(self):
        assert self._read(deadline=datetime(2026, 11, 15)).deadline.tzinfo is None

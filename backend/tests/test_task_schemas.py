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
        )
        assert task.id == 1

    def test_coerce_tags_from_strings(self):
        task = TaskRead(
            id=1, title="T", status="TODO", priority="LOW", urgency="NORMAL",
            tags=["work", "personal"],
        )
        assert task.tags == ["work", "personal"]

    def test_coerce_tags_from_orm_objects(self):
        class FakeTag:
            name = "work"

        task = TaskRead(
            id=2, title="T", status="TODO", priority="LOW", urgency="NORMAL",
            tags=[FakeTag()],
        )
        assert task.tags == ["work"]

    def test_coerce_tags_mixed(self):
        class FakeTag:
            def __init__(self, name):
                self.name = name

        task = TaskRead(
            id=3, title="T", status="TODO", priority="LOW", urgency="NORMAL",
            tags=[FakeTag("work"), "personal"],
        )
        assert task.tags == ["work", "personal"]

    def test_from_attributes_enabled(self):
        assert TaskRead.model_config.get("from_attributes") is True


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

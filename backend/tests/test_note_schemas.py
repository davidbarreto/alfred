import pytest
from app.features.organizer.notes.schemas import (
    NoteCreate,
    NoteUpdate,
    NoteRead,
    NoteFilters,
)


class TestNoteCreate:
    def test_required_title(self):
        note = NoteCreate(title="Meeting notes")
        assert note.title == "Meeting notes"

    def test_defaults(self):
        note = NoteCreate(title="Test")
        assert note.description == ""
        assert note.tags == []
        assert note.task_id is None

    def test_with_all_fields(self):
        note = NoteCreate(
            title="Full note",
            description="Some content here",
            tags=["work", "ideas"],
            task_id=42,
        )
        assert note.description == "Some content here"
        assert note.tags == ["work", "ideas"]
        assert note.task_id == 42


class TestNoteUpdate:
    def test_all_fields_optional(self):
        update = NoteUpdate()
        assert update.title is None
        assert update.description is None
        assert update.tags is None
        assert update.task_id is None

    def test_partial_update(self):
        update = NoteUpdate(title="Updated title")
        assert update.title == "Updated title"
        assert update.description is None

    def test_model_dump_excludes_unset(self):
        update = NoteUpdate(description="New content")
        dumped = update.model_dump(exclude_unset=True)
        assert "description" in dumped
        assert "title" not in dumped


class TestNoteRead:
    def test_from_dict(self):
        note = NoteRead(id=1, title="Test", description="", tags=[])
        assert note.id == 1

    def test_coerce_tags_from_strings(self):
        note = NoteRead(id=1, title="T", description="", tags=["work", "personal"])
        assert note.tags == ["work", "personal"]

    def test_coerce_tags_from_orm_objects(self):
        class FakeTag:
            name = "work"

        note = NoteRead(id=2, title="T", description="", tags=[FakeTag()])
        assert note.tags == ["work"]

    def test_coerce_tags_mixed(self):
        class FakeTag:
            def __init__(self, name):
                self.name = name

        note = NoteRead(id=3, title="T", description="", tags=[FakeTag("work"), "personal"])
        assert note.tags == ["work", "personal"]

    def test_from_attributes_enabled(self):
        assert NoteRead.model_config.get("from_attributes") is True


class TestNoteFilters:
    def test_defaults(self):
        filters = NoteFilters()
        assert filters.limit == 100
        assert filters.tags is None
        assert filters.task_id is None

    def test_custom_values(self):
        filters = NoteFilters(limit=10, tags=["work"], task_id=5)
        assert filters.limit == 10
        assert filters.tags == ["work"]
        assert filters.task_id == 5

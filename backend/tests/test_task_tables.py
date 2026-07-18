from app.features.organizer.tasks.tables import Task


def _make_task(**kwargs) -> Task:
    defaults = dict(provider_id="provider-1", title="Test", status="TODO", priority="LOW", urgency="NORMAL")
    defaults.update(kwargs)
    return Task(**defaults)


class TestSyncCompletedAt:
    def test_setting_status_done_sets_completed_at(self):
        task = _make_task(status="TODO")

        task.status = "DONE"

        assert task.completed_at is not None

    def test_creating_with_done_status_sets_completed_at(self):
        task = _make_task(status="DONE")

        assert task.completed_at is not None

    def test_reopening_done_task_clears_completed_at(self):
        task = _make_task(status="DONE")
        assert task.completed_at is not None

        task.status = "TODO"

        assert task.completed_at is None

    def test_redundant_done_assignment_does_not_reset_timestamp(self):
        task = _make_task(status="TODO")
        task.status = "DONE"
        first_completed_at = task.completed_at

        task.status = "DONE"

        assert task.completed_at == first_completed_at

    def test_non_done_transitions_leave_completed_at_alone(self):
        task = _make_task(status="TODO")

        task.status = "DOING"

        assert task.completed_at is None

from datetime import datetime
from unittest.mock import MagicMock

from app.features.organizer.tasks.ranking import task_priority_sort_key


def _make_task(priority="LOW", deadline=None):
    task = MagicMock()
    task.priority = priority
    task.deadline = deadline
    return task


class TestTaskPrioritySortKey:
    def test_priority_beats_overdue_date(self):
        now = datetime(2026, 7, 18, 12, 0)
        overdue_low = _make_task(priority="LOW", deadline=datetime(2020, 1, 1))
        undated_high = _make_task(priority="HIGH", deadline=None)

        tasks = [overdue_low, undated_high]
        tasks.sort(key=lambda t: task_priority_sort_key(t, now))

        assert tasks[0] is undated_high

    def test_overdue_before_not_overdue_within_same_priority(self):
        now = datetime(2026, 7, 18, 12, 0)
        overdue = _make_task(priority="MEDIUM", deadline=datetime(2020, 1, 1))
        upcoming = _make_task(priority="MEDIUM", deadline=datetime(2030, 1, 1))

        tasks = [upcoming, overdue]
        tasks.sort(key=lambda t: task_priority_sort_key(t, now))

        assert tasks[0] is overdue

    def test_earliest_deadline_first_within_same_priority_and_overdue_state(self):
        now = datetime(2026, 7, 18, 12, 0)
        later = _make_task(priority="LOW", deadline=datetime(2030, 6, 1))
        sooner = _make_task(priority="LOW", deadline=datetime(2030, 1, 1))

        tasks = [later, sooner]
        tasks.sort(key=lambda t: task_priority_sort_key(t, now))

        assert tasks[0] is sooner

    def test_unknown_priority_sorts_last(self):
        now = datetime(2026, 7, 18, 12, 0)
        known = _make_task(priority="LOW", deadline=None)
        unknown = _make_task(priority="WEIRD", deadline=None)

        tasks = [unknown, known]
        tasks.sort(key=lambda t: task_priority_sort_key(t, now))

        assert tasks[0] is known

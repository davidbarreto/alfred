def _task(id=1, title="Buy milk", status="TODO", priority="LOW", urgency="NORMAL",
          deadline=None, tags=None, recurrence_rule=None, created_at=None, completed_at=None,
          streak=None, total_completions=None, missed_count=None):
    return {
        "id": id, "title": title, "status": status, "priority": priority, "urgency": urgency,
        "deadline": deadline, "tags": tags or [], "recurrence_rule": recurrence_rule,
        "is_done_today": False, "is_done_in_cycle": False,
        "streak": streak, "total_completions": total_completions, "missed_count": missed_count,
        "created_at": created_at or "2026-07-01T00:00:00+00:00",
        "completed_at": completed_at,
    }


def _completion(task_id, occurrence_date):
    return {"id": task_id * 100, "task_id": task_id, "occurrence_date": occurrence_date, "completed_at": occurrence_date + "T09:00:00"}


def _fake_get(tasks=None, history=None):
    tasks = tasks or []
    history = history or []

    async def fake_get(path, params=None):
        if path == "/organizer/tasks":
            return tasks
        if path == "/organizer/tasks/history":
            return history
        return []

    return fake_get


class TestHabitStats:
    def test_computes_streak_and_heatmap(self, client, mock_api):
        tasks = [_task(id=1, title="Water plants", recurrence_rule="FREQ=DAILY", streak=5, missed_count=0)]
        mock_api["get"].side_effect = _fake_get(tasks=tasks, history=[_completion(1, "2026-08-01")])

        resp = client.get("/tasks/insights")

        assert resp.status_code == 200
        assert "Water plants" in resp.text
        assert "🔥 5" in resp.text

    def test_needs_attention_counts_missed_habits(self, client, mock_api):
        tasks = [
            _task(id=1, title="Water plants", recurrence_rule="FREQ=DAILY", missed_count=2),
            _task(id=2, title="Stretch", recurrence_rule="FREQ=DAILY", missed_count=0),
        ]
        mock_api["get"].side_effect = _fake_get(tasks=tasks)

        resp = client.get("/tasks/insights")

        assert resp.status_code == 200
        assert "Behind" in resp.text


class TestMissedOneOffTasks:
    def test_past_deadline_not_done_is_missed(self, client, mock_api):
        tasks = [_task(id=1, title="Pay rent", deadline="2020-01-01T00:00:00", status="TODO")]
        mock_api["get"].side_effect = _fake_get(tasks=tasks)

        resp = client.get("/tasks/insights")

        assert resp.status_code == 200
        assert "Pay rent" in resp.text
        assert "No overdue one-off tasks." not in resp.text

    def test_done_task_past_deadline_is_not_missed(self, client, mock_api):
        tasks = [_task(id=1, title="Pay rent", deadline="2020-01-01T00:00:00", status="DONE")]
        mock_api["get"].side_effect = _fake_get(tasks=tasks)

        resp = client.get("/tasks/insights")

        assert resp.status_code == 200
        assert "No overdue one-off tasks." in resp.text

    def test_future_deadline_is_not_missed(self, client, mock_api):
        tasks = [_task(id=1, title="Future task", deadline="2099-01-01T00:00:00", status="TODO")]
        mock_api["get"].side_effect = _fake_get(tasks=tasks)

        resp = client.get("/tasks/insights")

        assert resp.status_code == 200
        assert "No overdue one-off tasks." in resp.text

    def test_recurring_task_excluded_from_one_off_missed(self, client, mock_api):
        tasks = [_task(
            id=1, title="Water plants", deadline="2020-01-01T00:00:00",
            status="TODO", recurrence_rule="FREQ=DAILY",
        )]
        mock_api["get"].side_effect = _fake_get(tasks=tasks)

        resp = client.get("/tasks/insights")

        assert resp.status_code == 200
        assert "No overdue one-off tasks." in resp.text


class TestProductivityByWeekday:
    def test_buckets_completions_by_weekday_in_calendar_order(self, client, mock_api):
        # 2026-08-03 is a Monday, 2026-08-05 is a Wednesday
        tasks = [
            _task(id=1, title="A", status="DONE", completed_at="2026-08-05T10:00:00+00:00"),
            _task(id=2, title="B", status="DONE", completed_at="2026-08-03T10:00:00+00:00"),
        ]
        mock_api["get"].side_effect = _fake_get(tasks=tasks)

        resp = client.get("/tasks/insights")

        assert resp.status_code == 200
        mon_pos = resp.text.index('"Mon"')
        wed_pos = resp.text.index('"Wed"')
        assert mon_pos < wed_pos


class TestCompletionRateByPriority:
    def test_computes_rate_per_priority_excluding_recurring(self, client, mock_api):
        tasks = [
            _task(id=1, priority="HIGH", status="DONE"),
            _task(id=2, priority="HIGH", status="TODO"),
            _task(id=3, priority="LOW", status="DONE"),
            _task(id=4, priority="LOW", status="DONE", recurrence_rule="FREQ=DAILY"),
        ]
        mock_api["get"].side_effect = _fake_get(tasks=tasks)

        resp = client.get("/tasks/insights")

        assert resp.status_code == 200
        assert "Completion rate by priority" in resp.text
        assert "50" in resp.text  # HIGH: 1/2 done


class TestTimeToComplete:
    def test_buckets_by_created_to_completed_delta(self, client, mock_api):
        tasks = [
            _task(id=1, created_at="2026-08-01T00:00:00+00:00", completed_at="2026-08-01T00:30:00+00:00"),
            _task(id=2, created_at="2026-08-01T00:00:00+00:00", completed_at="2026-08-10T00:00:00+00:00"),
        ]
        mock_api["get"].side_effect = _fake_get(tasks=tasks)

        resp = client.get("/tasks/insights")

        assert resp.status_code == 200
        # tojson HTML-escapes "<"/">" for safe embedding inside <script>
        assert "\\u003c1h" in resp.text
        assert "\\u003e1wk" in resp.text

    def test_recurring_tasks_excluded(self, client, mock_api):
        tasks = [
            _task(id=1, created_at="2026-08-01T00:00:00+00:00", completed_at="2026-08-01T00:30:00+00:00",
                  recurrence_rule="FREQ=DAILY"),
        ]
        mock_api["get"].side_effect = _fake_get(tasks=tasks)

        resp = client.get("/tasks/insights")

        assert resp.status_code == 200
        assert "No data" in resp.text

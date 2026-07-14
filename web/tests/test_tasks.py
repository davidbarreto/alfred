import httpx


def _task(id=1, title="Buy milk", status="TODO", priority="LOW", urgency="NORMAL",
          deadline=None, tags=None, recurrence_rule=None):
    return {
        "id": id, "title": title, "status": status, "priority": priority, "urgency": urgency,
        "deadline": deadline, "tags": tags or [], "recurrence_rule": recurrence_rule,
        "is_done_today": False, "streak": None, "total_completions": None, "missed_count": None,
    }


class TestUpdateTask:
    def test_updates_task_and_renders_filtered_list(self, client, mock_api):
        mock_api["patch"].return_value = _task(id=3, title="Buy oat milk", priority="HIGH")
        mock_api["get"].return_value = [_task(id=3, title="Buy oat milk", priority="HIGH")]

        resp = client.patch("/tasks/3", data={
            "title": "Buy oat milk",
            "priority": "HIGH",
            "urgency": "NORMAL",
            "deadline": "2026-07-20",
            "tags": "groceries, urgent",
            "recurrence_rule": "",
        })

        assert resp.status_code == 200
        assert "Buy oat milk" in resp.text
        mock_api["patch"].assert_any_await("/organizer/tasks/3", json={
            "title": "Buy oat milk",
            "priority": "HIGH",
            "urgency": "NORMAL",
            "tags": ["groceries", "urgent"],
            "deadline": "2026-07-20",
            "recurrence_rule": None,
        })

    def test_clearing_deadline_and_recurrence_sends_null(self, client, mock_api):
        mock_api["patch"].return_value = _task(id=3)
        mock_api["get"].return_value = [_task(id=3)]

        resp = client.patch("/tasks/3", data={
            "title": "Buy milk",
            "priority": "LOW",
            "urgency": "NORMAL",
            "tags": "",
        })

        assert resp.status_code == 200
        mock_api["patch"].assert_any_await("/organizer/tasks/3", json={
            "title": "Buy milk",
            "priority": "LOW",
            "urgency": "NORMAL",
            "tags": [],
            "deadline": None,
            "recurrence_rule": None,
        })

    def test_returns_422_when_backend_update_fails(self, client, mock_api):
        request = httpx.Request("PATCH", "http://api/organizer/tasks/3")
        response = httpx.Response(404, json={"detail": "Task not found"}, request=request)
        mock_api["patch"].side_effect = httpx.HTTPStatusError("not found", request=request, response=response)

        resp = client.patch("/tasks/3", data={"title": "Buy milk"})

        assert resp.status_code == 422
        assert "Task not found" in resp.text

    def test_requires_authentication(self, anon_client):
        resp = anon_client.patch("/tasks/3", data={"title": "Buy milk"}, follow_redirects=False)

        assert resp.status_code == 302
        assert resp.headers["location"].startswith("/login")

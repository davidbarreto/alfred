import httpx


def _note(id=1, title="Groceries", content="Milk, eggs", tags=None, archived_at=None):
    return {
        "id": id, "title": title, "content": content, "tags": tags or [],
        "created_at": "2026-07-10T08:00:00", "updated_at": "2026-07-10T08:00:00",
        "archived_at": archived_at,
    }


class TestUpdateNote:
    def test_updates_note_and_renders_grid(self, client, mock_api):
        mock_api["patch"].return_value = _note(id=2, title="Groceries updated", tags=["home"])
        mock_api["get"].return_value = [_note(id=2, title="Groceries updated", tags=["home"])]

        resp = client.patch("/notes/2", data={
            "title": "Groceries updated",
            "content": "Milk, eggs, bread",
            "tags": "home",
        })

        assert resp.status_code == 200
        assert "Groceries updated" in resp.text
        mock_api["patch"].assert_any_await("/organizer/notes/2", json={
            "title": "Groceries updated",
            "content": "Milk, eggs, bread",
            "tags": ["home"],
        })

    def test_clearing_tags_sends_empty_list(self, client, mock_api):
        mock_api["patch"].return_value = _note(id=2, tags=[])
        mock_api["get"].return_value = [_note(id=2, tags=[])]

        resp = client.patch("/notes/2", data={"title": "Groceries", "content": "", "tags": ""})

        assert resp.status_code == 200
        mock_api["patch"].assert_any_await("/organizer/notes/2", json={
            "title": "Groceries",
            "content": "",
            "tags": [],
        })

    def test_returns_422_when_backend_update_fails(self, client, mock_api):
        request = httpx.Request("PATCH", "http://api/organizer/notes/2")
        response = httpx.Response(404, json={"detail": "Note not found"}, request=request)
        mock_api["patch"].side_effect = httpx.HTTPStatusError("not found", request=request, response=response)

        resp = client.patch("/notes/2", data={"title": "Groceries"})

        assert resp.status_code == 422
        assert "Note not found" in resp.text

    def test_requires_authentication(self, anon_client):
        resp = anon_client.patch("/notes/2", data={"title": "Groceries"}, follow_redirects=False)

        assert resp.status_code == 302
        assert resp.headers["location"].startswith("/login")


class TestNotesGridEditButton:
    def test_renders_edit_button_per_note(self, client, mock_api):
        mock_api["get"].return_value = [_note(id=5, title="Groceries")]

        resp = client.get("/notes/")

        assert resp.status_code == 200
        assert "openEditNote(" in resp.text


class TestArchiveNote:
    def test_archives_and_renders_grid(self, client, mock_api):
        mock_api["post"].return_value = _note(id=2, archived_at="2026-07-14T10:00:00")
        mock_api["get"].return_value = []

        resp = client.post("/notes/2/archive")

        assert resp.status_code == 200
        mock_api["post"].assert_any_await("/organizer/notes/2/archive")

    def test_excludes_archived_note_from_response(self, client, mock_api):
        mock_api["post"].return_value = _note(id=2, archived_at="2026-07-14T10:00:00")
        mock_api["get"].return_value = [_note(id=5, title="Still active")]

        resp = client.post("/notes/2/archive")

        assert resp.status_code == 200
        assert "Still active" in resp.text

    def test_returns_422_when_backend_fails(self, client, mock_api):
        request = httpx.Request("POST", "http://api/organizer/notes/2/archive")
        response = httpx.Response(404, json={"detail": "Note not found"}, request=request)
        mock_api["post"].side_effect = httpx.HTTPStatusError("not found", request=request, response=response)

        resp = client.post("/notes/2/archive")

        assert resp.status_code == 422

    def test_requires_authentication(self, anon_client):
        resp = anon_client.post("/notes/2/archive", follow_redirects=False)

        assert resp.status_code == 302
        assert resp.headers["location"].startswith("/login")


class TestUnarchiveNote:
    def test_unarchives_and_renders_grid(self, client, mock_api):
        mock_api["post"].return_value = _note(id=2)
        mock_api["get"].return_value = []

        resp = client.post("/notes/2/unarchive")

        assert resp.status_code == 200
        mock_api["post"].assert_any_await("/organizer/notes/2/unarchive")

    def test_returns_422_when_backend_fails(self, client, mock_api):
        request = httpx.Request("POST", "http://api/organizer/notes/2/unarchive")
        response = httpx.Response(404, json={"detail": "Note not found"}, request=request)
        mock_api["post"].side_effect = httpx.HTTPStatusError("not found", request=request, response=response)

        resp = client.post("/notes/2/unarchive")

        assert resp.status_code == 422

    def test_requires_authentication(self, anon_client):
        resp = anon_client.post("/notes/2/unarchive", follow_redirects=False)

        assert resp.status_code == 302
        assert resp.headers["location"].startswith("/login")


class TestArchivedNotesPage:
    def test_renders_archived_notes(self, client, mock_api):
        mock_api["get"].return_value = [_note(id=3, title="Old bug", archived_at="2026-07-01T00:00:00")]

        resp = client.get("/notes/archived")

        assert resp.status_code == 200
        assert "Old bug" in resp.text
        assert "unarchiveNote(" in resp.text
        assert 'onclick="archiveNote(' not in resp.text

    def test_requests_archived_true_from_api(self, client, mock_api):
        mock_api["get"].return_value = []

        client.get("/notes/archived")

        calls = mock_api["get"].call_args_list
        assert all(c.kwargs["params"]["archived"] == "true" for c in calls)

    def test_requires_authentication(self, anon_client):
        resp = anon_client.get("/notes/archived", follow_redirects=False)

        assert resp.status_code == 302
        assert resp.headers["location"].startswith("/login")


class TestNotesPagination:
    def test_shows_next_when_more_than_page_size(self, client, mock_api):
        mock_api["get"].return_value = [_note(id=i) for i in range(25)]

        resp = client.get("/notes/")

        assert resp.status_code == 200
        assert "changePage(1)" in resp.text

    def test_no_pagination_footer_for_short_list(self, client, mock_api):
        mock_api["get"].return_value = [_note(id=1)]

        resp = client.get("/notes/")

        assert resp.status_code == 200
        assert "changePage(1)" not in resp.text

    def test_offset_passed_to_api(self, client, mock_api):
        mock_api["get"].return_value = []

        client.get("/notes/?offset=24")

        calls = mock_api["get"].call_args_list
        assert any(c.kwargs["params"].get("offset") == 24 for c in calls)


class TestNotesTagFilter:
    def test_tags_query_param_passed_to_api(self, client, mock_api):
        mock_api["get"].return_value = []

        client.get("/notes/?tags=work&tags=bug")

        calls = mock_api["get"].call_args_list
        tagged_calls = [c for c in calls if c.kwargs["params"].get("tags")]
        assert tagged_calls
        assert tagged_calls[0].kwargs["params"]["tags"] == ["work", "bug"]

    def test_sort_query_param_passed_to_api(self, client, mock_api):
        mock_api["get"].return_value = []

        client.get("/notes/?sort=updated")

        calls = mock_api["get"].call_args_list
        assert any(c.kwargs["params"].get("sort") == "updated" for c in calls)

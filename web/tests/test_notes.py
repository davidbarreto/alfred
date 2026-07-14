import httpx


def _note(id=1, title="Groceries", content="Milk, eggs", tags=None):
    return {
        "id": id, "title": title, "content": content, "tags": tags or [],
        "created_at": "2026-07-10T08:00:00", "updated_at": "2026-07-10T08:00:00",
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

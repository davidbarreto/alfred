import httpx

_SETTINGS = {"user_name": "Sam", "persona_additions": "Sam plays the cello.", "base_persona": "# Alfred\n\nBasic persona."}


class TestPersonaPage:
    def test_shows_name_additions_and_base(self, client, mock_api):
        mock_api["get"].return_value = _SETTINGS

        resp = client.get("/persona")

        assert resp.status_code == 200
        assert 'value="Sam"' in resp.text
        assert "Sam plays the cello.</textarea>" in resp.text
        assert "Basic persona." in resp.text
        mock_api["get"].assert_awaited_once_with("/core/assistant-settings", params=None)

    def test_unavailable(self, client, mock_api):
        mock_api["get"].side_effect = httpx.ConnectError("down")

        assert "unavailable right now" in client.get("/persona").text


class TestSave:
    def test_forwards_to_backend(self, client, mock_api):
        mock_api["put"].return_value = _SETTINGS

        resp = client.put("/persona", json={"user_name": "Sam", "persona_additions": None})

        assert resp.status_code == 200
        mock_api["put"].assert_awaited_once_with(
            "/core/assistant-settings", json={"user_name": "Sam", "persona_additions": None}
        )

    def test_backend_error_is_relayed(self, client, mock_api):
        response = httpx.Response(409, json={"detail": "nope"})
        mock_api["put"].side_effect = httpx.HTTPStatusError("409", request=httpx.Request("PUT", "/"), response=response)

        resp = client.put("/persona", json={"user_name": "Sam"})

        assert resp.status_code == 409 and resp.json() == {"error": "nope"}

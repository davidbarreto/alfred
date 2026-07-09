import httpx


class TestPronounce:
    def test_streams_audio_from_backend(self, client, mock_api):
        mock_api["get_bytes"].return_value = (b"fake-mp3-bytes", "audio/mpeg")

        resp = client.get("/languages/fr/pronounce?text=bonjour")

        assert resp.status_code == 200
        assert resp.headers["content-type"] == "audio/mpeg"
        assert resp.content == b"fake-mp3-bytes"
        mock_api["get_bytes"].assert_awaited_once_with(
            "/language/chunks/pronunciation", {"text": "bonjour", "lang": "fr"}
        )

    def test_returns_502_when_backend_unreachable(self, client, mock_api):
        request = httpx.Request("GET", "http://api/language/chunks/pronunciation")
        mock_api["get_bytes"].side_effect = httpx.ConnectError("connection refused", request=request)

        resp = client.get("/languages/fr/pronounce?text=bonjour")

        assert resp.status_code == 502

    def test_requires_authentication(self, anon_client):
        resp = anon_client.get("/languages/fr/pronounce?text=bonjour", follow_redirects=False)

        assert resp.status_code == 302
        assert resp.headers["location"].startswith("/login")

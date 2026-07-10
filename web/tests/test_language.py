import httpx

from app.routes.language import _build_shadowing_chart, _shadowing_score


class TestShadowingScore:
    def test_prefers_ai_feedback_score(self):
        session = {"ai_feedback_json": {"score": 85}, "quality_score": 3.0}

        assert _shadowing_score(session) == 85

    def test_falls_back_to_quality_score_scaled_to_100(self):
        session = {"ai_feedback_json": None, "quality_score": 3.0}

        assert _shadowing_score(session) == 75.0

    def test_returns_none_when_no_score_available(self):
        assert _shadowing_score({"ai_feedback_json": None, "quality_score": None}) is None


class TestBuildShadowingChart:
    def test_returns_none_with_fewer_than_two_scored_attempts(self):
        assert _build_shadowing_chart([]) is None
        assert _build_shadowing_chart([{"created_at": "2026-01-01T00:00:00", "ai_feedback_json": {"score": 80}, "quality_score": None}]) is None

    def test_orders_points_oldest_to_newest(self):
        sessions = [
            {"created_at": "2026-01-03T00:00:00", "ai_feedback_json": {"score": 90}, "quality_score": None},
            {"created_at": "2026-01-02T00:00:00", "ai_feedback_json": {"score": 70}, "quality_score": None},
            {"created_at": "2026-01-01T00:00:00", "ai_feedback_json": {"score": 50}, "quality_score": None},
        ]

        chart = _build_shadowing_chart(sessions)

        assert [p["score"] for p in chart["points"]] == [50, 70, 90]
        assert [p["date"] for p in chart["points"]] == ["2026-01-01", "2026-01-02", "2026-01-03"]

    def test_skips_sessions_without_a_score(self):
        sessions = [
            {"created_at": "2026-01-02T00:00:00", "ai_feedback_json": {"score": 90}, "quality_score": None},
            {"created_at": "2026-01-01T00:00:00", "ai_feedback_json": None, "quality_score": None},
        ]

        chart = _build_shadowing_chart(sessions)

        assert chart is None  # only one scored attempt remains

    def test_polyline_matches_point_coordinates(self):
        sessions = [
            {"created_at": "2026-01-02T00:00:00", "ai_feedback_json": {"score": 100}, "quality_score": None},
            {"created_at": "2026-01-01T00:00:00", "ai_feedback_json": {"score": 0}, "quality_score": None},
        ]

        chart = _build_shadowing_chart(sessions)

        expected = " ".join(f"{p['x']},{p['y']}" for p in chart["points"])
        assert chart["polyline"] == expected


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


class TestSessionAudio:
    def test_streams_audio_from_backend(self, client, mock_api):
        mock_api["get_bytes"].return_value = (b"fake-ogg-bytes", "audio/ogg")

        resp = client.get("/languages/fr/sessions/7/audio")

        assert resp.status_code == 200
        assert resp.headers["content-type"] == "audio/ogg"
        assert resp.content == b"fake-ogg-bytes"
        mock_api["get_bytes"].assert_awaited_once_with("/language/sessions/7/audio")

    def test_returns_502_when_backend_unreachable(self, client, mock_api):
        request = httpx.Request("GET", "http://api/language/sessions/7/audio")
        mock_api["get_bytes"].side_effect = httpx.ConnectError("connection refused", request=request)

        resp = client.get("/languages/fr/sessions/7/audio")

        assert resp.status_code == 502

    def test_requires_authentication(self, anon_client):
        resp = anon_client.get("/languages/fr/sessions/7/audio", follow_redirects=False)

        assert resp.status_code == 302
        assert resp.headers["location"].startswith("/login")


class TestSubmitShadowing:
    def test_uploads_audio_and_returns_result(self, client, mock_api):
        mock_api["get"].return_value = [{"id": 5, "code": "fr", "name": "French"}]
        mock_api["post_multipart"].return_value = {"id": 9, "quality_score": 3.6}

        resp = client.post(
            "/languages/fr/chunks/42/shadow",
            files={"audio": ("recording.webm", b"fake-audio-bytes", "audio/webm")},
        )

        assert resp.status_code == 200
        assert resp.json() == {"id": 9, "quality_score": 3.6}
        mock_api["post_multipart"].assert_awaited_once()
        call = mock_api["post_multipart"].call_args
        assert call.args[0] == "/language/sessions/shadowing/audio"
        assert call.kwargs["data"] == {"track_id": 5, "chunk_id": 42}
        assert call.kwargs["files"]["audio"][1] == b"fake-audio-bytes"

    def test_returns_404_when_track_not_found(self, client, mock_api):
        mock_api["get"].return_value = []

        resp = client.post(
            "/languages/xx/chunks/42/shadow",
            files={"audio": ("recording.webm", b"fake-audio-bytes", "audio/webm")},
        )

        assert resp.status_code == 404

    def test_returns_400_when_no_audio_provided(self, client, mock_api):
        mock_api["get"].return_value = [{"id": 5, "code": "fr", "name": "French"}]

        resp = client.post("/languages/fr/chunks/42/shadow", data={})

        assert resp.status_code == 400

    def test_returns_502_when_backend_unreachable(self, client, mock_api):
        mock_api["get"].return_value = [{"id": 5, "code": "fr", "name": "French"}]
        request = httpx.Request("POST", "http://api/language/sessions/shadowing/audio")
        mock_api["post_multipart"].side_effect = httpx.ConnectError("connection refused", request=request)

        resp = client.post(
            "/languages/fr/chunks/42/shadow",
            files={"audio": ("recording.webm", b"fake-audio-bytes", "audio/webm")},
        )

        assert resp.status_code == 502

    def test_requires_authentication(self, anon_client):
        resp = anon_client.post(
            "/languages/fr/chunks/42/shadow",
            files={"audio": ("recording.webm", b"fake-audio-bytes", "audio/webm")},
            follow_redirects=False,
        )

        assert resp.status_code == 302
        assert resp.headers["location"].startswith("/login")


class TestShadowSession:
    def test_renders_due_chunks_from_daily_batch(self, client, mock_api):
        mock_api["get"].side_effect = [
            [{"id": 5, "code": "fr", "name": "French", "daily_quota": 10}],
            [{"track_id": 5, "track_code": "fr", "total_due": 2,
              "chunks": [{"id": 42, "text": "bonjour", "translation": "hello"}]}],
        ]

        resp = client.get("/languages/fr/shadow")

        assert resp.status_code == 200
        assert "bonjour" in resp.text
        mock_api["get"].assert_any_await("/language/chunks/daily-batch", params={"track_id": 5})

    def test_renders_empty_state_when_nothing_due(self, client, mock_api):
        mock_api["get"].side_effect = [
            [{"id": 5, "code": "fr", "name": "French", "daily_quota": 10}],
            [],
        ]

        resp = client.get("/languages/fr/shadow")

        assert resp.status_code == 200
        assert "Nothing due right now." in resp.text

    def test_returns_404_when_track_not_found(self, client, mock_api):
        mock_api["get"].return_value = []

        resp = client.get("/languages/xx/shadow")

        assert resp.status_code == 404

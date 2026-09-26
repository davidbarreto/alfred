import httpx

_TS = "2026-09-26T10:00:00Z"


def _story(id=1, situation="Legacy service kept timing out", tags=None, strength=3):
    return {
        "id": id, "situation": situation, "task": "Stabilise it", "action": "Added caching",
        "result": "p99 halved", "strength": strength, "tags": tags or [], "created_at": _TS, "updated_at": _TS,
    }


def _by_path(mapping):
    def _side_effect(path, *args, **kwargs):
        for prefix, value in mapping.items():
            if path == prefix:
                return value
        raise AssertionError(f"unexpected GET {path}")
    return _side_effect


def _status_error(status_code: int, detail: str) -> httpx.HTTPStatusError:
    request = httpx.Request("POST", "http://api")
    return httpx.HTTPStatusError("err", request=request, response=httpx.Response(status_code, json={"detail": detail}, request=request))


class TestStoriesPage:
    def test_story_text_is_escaped_not_injected_into_js(self, client, mock_api):
        mock_api["get"].side_effect = _by_path({
            "/organizer/interview-stories": [_story(situation="It's <script>alert(1)</script>")],
            "/organizer/interview-stories/tags": [],
        })

        resp = client.get("/interview-prep/stories")

        assert resp.status_code == 200
        assert "<script>alert(1)</script>" not in resp.text
        assert "&lt;script&gt;" in resp.text
        assert "showStory(1)" in resp.text

    def test_create_sends_parsed_tags(self, client, mock_api):
        resp = client.post(
            "/interview-prep/stories",
            data={"situation": "s", "task": "t", "action": "a", "result": "r", "strength": "4", "tags": "Leadership, , Ops"},
            follow_redirects=False,
        )

        assert resp.status_code == 303
        payload = mock_api["post"].await_args.kwargs["json"]
        assert payload["tags"] == ["Leadership", "Ops"]
        assert payload["strength"] == 4

    def test_create_failure_surfaces_backend_detail(self, client, mock_api):
        mock_api["post"].side_effect = _status_error(422, "strength out of range")

        resp = client.post(
            "/interview-prep/stories",
            data={"situation": "s", "task": "t", "action": "a", "result": "r"},
            follow_redirects=False,
        )

        assert resp.status_code == 303
        assert "error=strength+out+of+range" in resp.headers["location"]

    def test_add_tag_url_encodes_tag(self, client, mock_api):
        client.post("/interview-prep/stories/3/tags", data={"tag": "CI/CD"}, follow_redirects=False)
        mock_api["post"].assert_awaited_once_with("/organizer/interview-stories/3/tags/CI%2FCD")


class TestPrepQuestionDetail:
    def test_shows_linked_stories_and_only_unlinked_in_picker(self, client, mock_api):
        linked = {**_story(id=1, situation="Linked story"), "fit_score": 5}
        mock_api["get"].side_effect = _by_path({
            "/organizer/interview-prep-questions/7": {
                "id": 7, "text": "Tell me about a conflict", "stories": [linked], "created_at": _TS, "updated_at": _TS,
            },
            "/organizer/interview-stories": [_story(id=1, situation="Linked story"), _story(id=2, situation="Free story")],
        })

        resp = client.get("/interview-prep/prep-questions/7")

        assert resp.status_code == 200
        assert "Fit: 5 - Excellent" in resp.text
        assert '<option value="2">' in resp.text
        assert '<option value="1">' not in resp.text

    def test_link_puts_fit_score(self, client, mock_api):
        resp = client.post(
            "/interview-prep/prep-questions/7/link", data={"story_id": "2", "fit_score": "4"}, follow_redirects=False
        )

        assert resp.status_code == 303
        mock_api["put"].assert_awaited_once_with(
            "/organizer/interview-prep-questions/7/stories/2", json={"fit_score": 4}
        )

    def test_unlink(self, client, mock_api):
        client.post("/interview-prep/prep-questions/7/stories/2/unlink", follow_redirects=False)
        mock_api["delete"].assert_awaited_once_with("/organizer/interview-prep-questions/7/stories/2")


class TestCandidateQuestionsPage:
    def test_groups_by_category(self, client, mock_api):
        mock_api["get"].side_effect = _by_path({
            "/organizer/candidate-questions": [
                {"id": 1, "text": "How is on-call run?", "category": "Tech", "created_at": _TS, "updated_at": _TS},
                {"id": 2, "text": "What's the stack?", "category": "Tech", "created_at": _TS, "updated_at": _TS},
                {"id": 3, "text": "Remote days?", "category": "Work-life", "created_at": _TS, "updated_at": _TS},
            ],
            "/organizer/candidate-questions/categories": ["Tech", "Work-life"],
        })

        resp = client.get("/interview-prep/candidate-questions")

        assert resp.status_code == 200
        assert resp.text.count('<div class="divider my-2">Tech</div>') == 1
        assert resp.text.count('<div class="divider my-2">Work-life</div>') == 1
        assert '<option value="Logistics">' in resp.text

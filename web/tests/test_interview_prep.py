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
        assert resp.text.count('uppercase tracking-wide mb-1.5">Tech</h2>') == 1
        assert resp.text.count('uppercase tracking-wide mb-1.5">Work-life</h2>') == 1
        assert '<option value="Logistics">' in resp.text


class TestEditDeleteStories:
    def test_edit_patches_story_with_parsed_tags(self, client, mock_api):
        resp = client.post(
            "/interview-prep/stories/3/edit",
            data={"situation": "s", "task": "t", "action": "a", "result": "r", "strength": "4", "tags": "Lead, ,Conflict"},
            follow_redirects=False,
        )

        assert resp.status_code == 303
        mock_api["patch"].assert_awaited_once_with(
            "/organizer/interview-stories/3",
            json={"situation": "s", "task": "t", "action": "a", "result": "r", "strength": 4, "tags": ["Lead", "Conflict"]},
        )

    def test_edit_failure_surfaces_backend_detail(self, client, mock_api):
        mock_api["patch"].side_effect = _status_error(404, "Story not found")

        resp = client.post(
            "/interview-prep/stories/3/edit",
            data={"situation": "s", "task": "t", "action": "a", "result": "r"},
            follow_redirects=False,
        )

        assert "error=Story+not+found" in resp.headers["location"]

    def test_page_prefills_edit_form(self, client, mock_api):
        mock_api["get"].side_effect = _by_path({
            "/organizer/interview-stories": [_story(tags=[{"tag": "Lead"}, {"tag": "Conflict"}])],
            "/organizer/interview-stories/tags": [],
        })

        resp = client.get("/interview-prep/stories")

        assert 'action="/interview-prep/stories/1/edit"' in resp.text
        assert 'value="Lead, Conflict"' in resp.text

    def test_delete_story(self, client, mock_api):
        client.post("/interview-prep/stories/3/delete", follow_redirects=False)
        mock_api["delete"].assert_awaited_once_with("/organizer/interview-stories/3")


class TestEditDeletePrepQuestions:
    def test_edit_from_list_redirects_to_list(self, client, mock_api):
        resp = client.post("/interview-prep/prep-questions/7/edit", data={"text": "New"}, follow_redirects=False)

        mock_api["patch"].assert_awaited_once_with("/organizer/interview-prep-questions/7", json={"text": "New"})
        assert resp.headers["location"] == "/interview-prep/prep-questions"

    def test_edit_from_detail_redirects_to_detail(self, client, mock_api):
        resp = client.post(
            "/interview-prep/prep-questions/7/edit", data={"text": "New", "back": "detail"}, follow_redirects=False
        )

        assert resp.headers["location"] == "/interview-prep/prep-questions/7"

    def test_delete_redirects_to_list(self, client, mock_api):
        resp = client.post("/interview-prep/prep-questions/7/delete", follow_redirects=False)

        mock_api["delete"].assert_awaited_once_with("/organizer/interview-prep-questions/7")
        assert resp.headers["location"] == "/interview-prep/prep-questions"

    def test_delete_failure_surfaces_backend_detail(self, client, mock_api):
        mock_api["delete"].side_effect = _status_error(404, "Question not found")

        resp = client.post("/interview-prep/prep-questions/7/delete", follow_redirects=False)

        assert "error=Question+not+found" in resp.headers["location"]


class TestEditDeleteCandidateQuestions:
    def test_edit_patches_text_and_category(self, client, mock_api):
        client.post(
            "/interview-prep/candidate-questions/4/edit", data={"text": "Q?", "category": "Tech"}, follow_redirects=False
        )

        mock_api["patch"].assert_awaited_once_with(
            "/organizer/candidate-questions/4", json={"text": "Q?", "category": "Tech"}
        )

    def test_delete(self, client, mock_api):
        client.post("/interview-prep/candidate-questions/4/delete", follow_redirects=False)

        mock_api["delete"].assert_awaited_once_with("/organizer/candidate-questions/4")

    def test_page_renders_edit_and_delete_per_question(self, client, mock_api):
        mock_api["get"].side_effect = _by_path({
            "/organizer/candidate-questions": [
                {"id": 4, "text": "Stack?", "category": "Tech", "created_at": _TS, "updated_at": _TS},
            ],
            "/organizer/candidate-questions/categories": ["Tech"],
        })

        resp = client.get("/interview-prep/candidate-questions")

        assert 'action="/interview-prep/candidate-questions/4/edit"' in resp.text
        assert 'action="/interview-prep/candidate-questions/4/delete"' in resp.text
        assert '<option value="Tech" selected>' in resp.text


class TestPrepQuestionsList:
    def test_shows_linked_story_count_per_question(self, client, mock_api):
        mock_api["get"].side_effect = _by_path({
            "/organizer/interview-prep-questions": [
                {"id": 1, "text": "Q one", "story_count": 3, "created_at": _TS, "updated_at": _TS},
                {"id": 2, "text": "Q two", "story_count": 0, "created_at": _TS, "updated_at": _TS},
            ],
        })

        resp = client.get("/interview-prep/prep-questions")

        assert 'title="3 linked stories">3</span>' in resp.text
        assert 'title="0 linked stories">0</span>' in resp.text


class TestScoreBadgeColors:
    def test_strength_and_fit_badges_use_a_distinct_color_per_score(self, client, mock_api):
        mock_api["get"].side_effect = _by_path({
            "/organizer/interview-stories": [_story(id=1, strength=5), _story(id=2, strength=1)],
            "/organizer/interview-stories/tags": [],
        })

        resp = client.get("/interview-prep/stories")

        assert "text-[#0F7B58]" in resp.text and "Strength 5/5" in resp.text
        assert "text-[#B93636]" in resp.text and "Strength 1/5" in resp.text

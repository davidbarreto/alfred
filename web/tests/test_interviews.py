def _process(id=1, company_id=1, role_title="Backend Engineer", status="active", stages=None):
    return {
        "id": id, "company_id": company_id, "role_title": role_title, "status": status,
        "source": None, "applied_date": None, "priority": None, "department": None, "notes": None, "study_plan_id": None,
        "salary_min": None, "salary_max": None, "salary_currency": None, "work_regime": None,
        "office_days_per_month": None, "office_location": None, "benefits": None,
        "job_description_url": None, "company_feedback": None,
        "stages": stages or [],
        "created_at": "2026-09-01T10:00:00", "updated_at": "2026-09-01T10:00:00",
    }


def _company(id=1, name="Acme", website=None, notes=None):
    return {"id": id, "name": name, "website": website, "notes": notes,
            "created_at": "2026-09-01T10:00:00", "updated_at": "2026-09-01T10:00:00"}


def _stage(id=1, process_id=1, stage_type="phone_screen", status="scheduled"):
    return {
        "id": id, "process_id": process_id, "stage_type": stage_type, "scheduled_at": None,
        "status": status, "feedback": None, "notes": None, "sequence": 0, "calendar_event_id": None,
        "created_at": "2026-09-01T10:00:00", "updated_at": "2026-09-01T10:00:00",
    }


def _by_path(mapping, default=None):
    """A get()/post()/patch() side_effect keyed by the first positional arg (the URL path)."""
    def _side_effect(path, *args, **kwargs):
        for prefix, value in mapping.items():
            if path == prefix or path.startswith(prefix):
                return value
        return default
    return _side_effect


class TestCompaniesPage:
    def test_renders_list(self, client, mock_api):
        mock_api["get"].return_value = [_company(name="Acme Corp")]
        resp = client.get("/interviews/companies")
        assert resp.status_code == 200
        assert "Acme Corp" in resp.text

    def test_create_company_posts_payload(self, client, mock_api):
        mock_api["post"].return_value = _company(id=2, name="New Co")
        resp = client.post("/interviews/companies", data={"name": "New Co", "website": ""}, follow_redirects=False)
        assert resp.status_code == 303
        assert resp.headers["location"] == "/interviews/companies"
        mock_api["post"].assert_awaited_once_with("/organizer/interview-companies", json={"name": "New Co"})


class TestCompanyDetail:
    def test_renders_company_and_processes(self, client, mock_api):
        mock_api["get"].side_effect = _by_path({
            "/organizer/interview-companies/1": _company(id=1, name="Acme Corp"),
            "/organizer/interview-processes": [_process(role_title="Staff Engineer")],
        }, default=[])
        resp = client.get("/interviews/companies/1")
        assert resp.status_code == 200
        assert "Acme Corp" in resp.text
        assert "Staff Engineer" in resp.text

    def test_update_posts_payload(self, client, mock_api):
        mock_api["patch"].return_value = _company(id=1, name="Acme Renamed")
        resp = client.post(
            "/interviews/companies/1/update",
            data={"name": "Acme Renamed", "website": "https://acme.example", "notes": ""},
            follow_redirects=False,
        )
        assert resp.status_code == 303
        mock_api["patch"].assert_awaited_once_with(
            "/organizer/interview-companies/1",
            json={"name": "Acme Renamed", "website": "https://acme.example", "notes": None},
        )

    def test_delete_redirects_to_list(self, client, mock_api):
        resp = client.post("/interviews/companies/1/delete", follow_redirects=False)
        assert resp.status_code == 303
        assert resp.headers["location"] == "/interviews/companies"
        mock_api["delete"].assert_awaited_once_with("/organizer/interview-companies/1")


class TestInterviewsTable:
    def test_shows_current_stage_progress(self, client, mock_api):
        stages = [
            _stage(id=1, status="passed"),
            _stage(id=2, status="scheduled"),
            _stage(id=3, status="scheduled"),
        ]
        mock_api["get"].side_effect = _by_path({
            "/organizer/interview-processes": [_process(stages=stages)],
            "/organizer/interview-companies": [_company(name="Acme Corp")],
            "/organizer/interview-insights": [],
        }, default=[])
        resp = client.get("/interviews/table")
        assert resp.status_code == 200
        assert "2/3" in resp.text

    def test_shows_final_stage_when_none_scheduled(self, client, mock_api):
        stages = [_stage(id=1, status="passed"), _stage(id=2, status="passed")]
        mock_api["get"].side_effect = _by_path({
            "/organizer/interview-processes": [_process(stages=stages)],
            "/organizer/interview-companies": [_company(name="Acme Corp")],
            "/organizer/interview-insights": [],
        }, default=[])
        resp = client.get("/interviews/table")
        assert resp.status_code == 200
        assert "2/2" in resp.text


class TestCreateProcess:
    def test_create_posts_department(self, client, mock_api):
        mock_api["post"].return_value = _process()
        resp = client.post(
            "/interviews/",
            data={
                "company_id": "1", "role_title": "Backend Engineer", "department": "Platform Engineering",
            },
            follow_redirects=False,
        )
        assert resp.status_code == 303
        payload = mock_api["post"].call_args.kwargs["json"]
        assert payload["process"]["department"] == "Platform Engineering"

    def test_create_omits_department_when_blank(self, client, mock_api):
        mock_api["post"].return_value = _process()
        resp = client.post(
            "/interviews/",
            data={"company_id": "1", "role_title": "Backend Engineer", "department": ""},
            follow_redirects=False,
        )
        assert resp.status_code == 303
        payload = mock_api["post"].call_args.kwargs["json"]
        assert "department" not in payload["process"]


class TestUpdateProcessStatus:
    def test_patches_status_and_redirects_back(self, client, mock_api):
        mock_api["patch"].return_value = _process(status="active")
        resp = client.post(
            "/interviews/1/status",
            data={"status": "active"},
            headers={"referer": "http://testserver/interviews?status=applied"},
            follow_redirects=False,
        )
        assert resp.status_code == 303
        assert resp.headers["location"] == "/interviews?status=applied"
        mock_api["patch"].assert_awaited_once_with(
            "/organizer/interview-processes/1", json={"status": "active"}
        )


class TestProcessEdit:
    def test_renders_prefilled_form(self, client, mock_api):
        mock_api["get"].side_effect = _by_path({
            "/organizer/interview-processes/1": _process(role_title="Staff Engineer"),
            "/organizer/interview-companies": [_company(name="Acme Corp")],
        })
        resp = client.get("/interviews/1/edit")
        assert resp.status_code == 200
        assert "Staff Engineer" in resp.text
        assert "Acme Corp" in resp.text

    def test_update_posts_full_payload(self, client, mock_api):
        mock_api["patch"].return_value = _process()
        resp = client.post(
            "/interviews/1/update",
            data={
                "company_id": "1", "role_title": "Principal Engineer", "status": "offer",
                "priority": "high", "department": "Platform", "source": "", "applied_date": "", "work_regime": "remote",
                "office_days_per_month": "", "office_location": "", "salary_min": "", "salary_max": "",
                "salary_currency": "", "benefits": "", "job_description_url": "",
            },
            follow_redirects=False,
        )
        assert resp.status_code == 303
        assert resp.headers["location"] == "/interviews/1"
        payload = mock_api["patch"].call_args.kwargs["json"]
        assert payload["role_title"] == "Principal Engineer"
        assert payload["status"] == "offer"
        assert payload["priority"] == "high"
        assert payload["department"] == "Platform"
        assert payload["work_regime"] == "remote"
        assert payload["source"] is None

    def test_renders_form_with_back_url_from_referer(self, client, mock_api):
        mock_api["get"].side_effect = _by_path({
            "/organizer/interview-processes/1": _process(role_title="Staff Engineer"),
            "/organizer/interview-companies": [_company(name="Acme Corp")],
        })
        resp = client.get("/interviews/1/edit", headers={"referer": "http://testserver/interviews/companies/1"})
        assert resp.status_code == 200
        assert 'action="/interviews/1/update"' in resp.text
        assert 'value="/interviews/companies/1"' in resp.text

    def test_update_redirects_to_back_url(self, client, mock_api):
        mock_api["patch"].return_value = _process()
        resp = client.post(
            "/interviews/1/update",
            data={
                "back_url": "/interviews/companies/1",
                "company_id": "1", "role_title": "Principal Engineer", "status": "offer",
                "priority": "", "source": "", "applied_date": "", "work_regime": "",
                "office_days_per_month": "", "office_location": "", "salary_min": "", "salary_max": "",
                "salary_currency": "", "benefits": "", "job_description_url": "",
            },
            follow_redirects=False,
        )
        assert resp.status_code == 303
        assert resp.headers["location"] == "/interviews/companies/1"

    def test_update_ignores_unsafe_back_url(self, client, mock_api):
        mock_api["patch"].return_value = _process()
        resp = client.post(
            "/interviews/1/update",
            data={
                "back_url": "https://evil.example",
                "company_id": "1", "role_title": "Principal Engineer", "status": "offer",
                "priority": "", "source": "", "applied_date": "", "work_regime": "",
                "office_days_per_month": "", "office_location": "", "salary_min": "", "salary_max": "",
                "salary_currency": "", "benefits": "", "job_description_url": "",
            },
            follow_redirects=False,
        )
        assert resp.status_code == 303
        assert resp.headers["location"] == "/interviews/1"


class TestProcessDetailLinks:
    def _mock_detail_gets(self, mock_api, stages):
        process = _process(stages=stages)
        mapping = {
            "/organizer/interview-processes/1": process,
            "/organizer/interview-companies/1": _company(),
            "/organizer/interview-links": [],
        }
        for s in stages:
            mapping[f"/organizer/interview-stages/{s['id']}/contacts"] = []
            mapping[f"/organizer/interview-stages/{s['id']}/tasks"] = []
            mapping[f"/organizer/interview-stages/{s['id']}/notes"] = []
        mock_api["get"].side_effect = _by_path(mapping, default=[])

    def test_renders_stage_with_no_links(self, client, mock_api):
        self._mock_detail_gets(mock_api, [_stage()])
        resp = client.get("/interviews/1")
        assert resp.status_code == 200
        assert "Phone screen" in resp.text

    def test_mark_passed_sends_status(self, client, mock_api):
        mock_api["patch"].return_value = _stage(status="passed")
        resp = client.post("/interviews/1/stages/1/update", data={"status": "passed"}, follow_redirects=False)
        assert resp.status_code == 303
        mock_api["patch"].assert_awaited_once_with("/organizer/interview-stages/1", json={"status": "passed"})

    def test_link_task_calls_backend(self, client, mock_api):
        resp = client.post("/interviews/1/stages/1/tasks/5/link", follow_redirects=False)
        assert resp.status_code == 303
        mock_api["post"].assert_awaited_once_with("/organizer/interview-stages/1/tasks/5")

    def test_unlink_task_calls_backend(self, client, mock_api):
        resp = client.post("/interviews/1/stages/1/tasks/5/unlink", follow_redirects=False)
        assert resp.status_code == 303
        mock_api["delete"].assert_awaited_once_with("/organizer/interview-stages/1/tasks/5")

    def test_create_and_link_task(self, client, mock_api):
        mock_api["post"].side_effect = _by_path({
            "/organizer/tasks": {"id": 42, "title": "Prep for onsite"},
        })
        resp = client.post("/interviews/1/stages/1/tasks/new", data={"title": "Prep for onsite"}, follow_redirects=False)
        assert resp.status_code == 303
        calls = mock_api["post"].call_args_list
        assert calls[0].args[0] == "/organizer/tasks"
        assert calls[0].kwargs["json"] == {"title": "Prep for onsite"}
        assert calls[1].args[0] == "/organizer/interview-stages/1/tasks/42"

    def test_link_event_patches_stage(self, client, mock_api):
        resp = client.post("/interviews/1/stages/1/event/7/link", follow_redirects=False)
        assert resp.status_code == 303
        mock_api["patch"].assert_awaited_once_with("/organizer/interview-stages/1", json={"calendar_event_id": 7})

    def test_unlink_event_clears_stage_field(self, client, mock_api):
        resp = client.post("/interviews/1/stages/1/event/unlink", follow_redirects=False)
        assert resp.status_code == 303
        mock_api["patch"].assert_awaited_once_with("/organizer/interview-stages/1", json={"calendar_event_id": None})


class TestSearchProxies:
    def test_search_tasks_passes_q_and_status(self, client, mock_api):
        mock_api["get"].return_value = [{"id": 1, "title": "Prep resume"}]
        resp = client.get("/interviews/1/stages/1/search/tasks?q=prep")
        assert resp.status_code == 200
        assert "Prep resume" in resp.text
        mock_api["get"].assert_awaited_once_with("/organizer/tasks", params={"q": "prep", "status": "ACTIVE", "limit": 8})

    def test_search_contacts_passes_name_param(self, client, mock_api):
        mock_api["get"].return_value = [{"id": 3, "name": "Jane Recruiter"}]
        resp = client.get("/interviews/1/stages/1/search/contacts?q=jane")
        assert resp.status_code == 200
        assert "Jane Recruiter" in resp.text
        mock_api["get"].assert_awaited_once_with("/organizer/contacts", params={"name": "jane", "limit": 8})

    def test_search_empty_query_skips_api_call(self, client, mock_api):
        resp = client.get("/interviews/1/stages/1/search/tasks")
        assert resp.status_code == 200
        mock_api["get"].assert_not_awaited()

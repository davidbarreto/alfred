import copy
import json
import re
from pathlib import Path

import httpx
import pytest

from app.shared.settings_page import SaveError, build_sections, plan_writes, read_paths, unregistered_preview

# Generated from the backend's build_catalog (defaults only, no stored values but two unregistered keys).
CATALOG = json.loads((Path(__file__).parent / "fixtures" / "settings_catalog.json").read_text())

_CITY = {"id": 3, "name": "Lisbon", "country": {"id": 1, "name": "Portugal", "code": "PT"}}
VALUES = {
    "/planning/settings": {
        "wake_time": "07:00", "sleep_time": None, "work_target_minutes": 420, "preferred_work_windows": ["09:00-12:00"],
        "workdays": ["mon", "tue", "wed", "thu", "fri"], "work_tag": "work", "office_tag": "office",
        "office_days_per_week": None, "office_min_minutes": None, "conventions": "No meetings before 9.",
        "travel_times": [{"origin": "home", "place": "office", "mode": "metro", "minutes": 30}],
        "default_travel_minutes": 30, "walk_tolerance_minutes": 10,
    },
    "/core/reminder-settings": {
        "overload_overdue_threshold": 5, "overload_urgent_threshold": 4, "overload_max_listed": 5,
        "overload_urgent_interval_hours": 4, "overdue_grace_hours_high": 0, "overdue_grace_hours_medium": 48,
        "overdue_grace_hours_low": 168, "undated_escalation_days_high": 7, "undated_escalation_days_medium": 21,
        "undated_escalation_days_low": 45, "catchup_tasks_per_day": 3, "catchup_stale_days": 30,
        "catchup_missed_habit_threshold": 3, "urgency_reset_days": 7, "undated_task_snooze_days": 7,
    },
    "/travel/settings": {
        "airport_buffer_min": 100, "home_to_airport_min": 45, "home_address": "1 Example Street",
        "home_city_id": 3, "home_city": _CITY, "max_visits_per_day": 4, "visit_duration_min": 90,
        "unpaid_leg_days": 30, "snooze_other_events": True,
    },
    "/finance/settings": {"cycle_start_day": 1},
    "/study/settings": {"max_active_plans": 3},
    "/organizer/calendar-notification-settings": {"profiles": {
        "cant_miss": ["7d", "3d", "1d", "4h", "1h", "30m", "10m", "5m", "0"], "important": ["1d", "4h", "1h", "15m", "0"],
        "normal": ["1h", "10m", "0"], "light": ["10m", "0"], "aware": ["3d", "1d"],
    }},
    "/organizer/contact-birthday-settings": {"relationships": {
        "family": ["1mo", "15d", "7d", "5d", "1d"], "relative": ["15d", "7d", "1d"], "friend": ["7d", "1d"], "other": ["3d"],
    }},
    "/core/assistant-settings": {
        "user_name": "Sam", "persona_additions": "SECRET-PERSONA-TEXT", "base_persona": "# Alfred",
    },
}


def _rows(sections):
    return {row["key"]: row for s in sections for g in s["groups"] for row in g["rows"]}


def _section(sections, namespace):
    return next(s for s in sections if s["namespace"] == namespace)


def _get(values=None, catalog=CATALOG):
    values = VALUES if values is None else values

    async def get(path, params=None):
        if path == "/core/settings/catalog":
            if catalog is None:
                raise httpx.ConnectError("down")
            return catalog
        if values.get(path) is None:
            raise httpx.ConnectError("down")
        return values[path]

    return get


class TestBuildSections:
    def test_reads_each_namespace_once(self):
        paths = read_paths(CATALOG)
        assert len(paths) == len(set(paths)) == len(VALUES)

    def test_values_and_modified_badge(self):
        rows = _rows(build_sections(CATALOG, VALUES))
        assert rows["travel.airport_buffer_min"]["value"] == 100
        assert rows["travel.airport_buffer_min"]["modified"] is True
        assert rows["travel.home_to_airport_min"]["modified"] is False
        assert rows["planning.work_target_minutes"]["modified"] is True

    def test_fields_without_default_are_never_modified(self):
        rows = _rows(build_sections(CATALOG, VALUES))
        assert rows["planning.wake_time"]["modified"] is False
        assert rows["travel.home_city_id"]["modified"] is False

    def test_cascade_modified_when_one_profile_differs(self):
        rows = _rows(build_sections(CATALOG, VALUES))
        assert rows["organizer.calendar_notification_cascades"]["modified"] is True
        assert rows["organizer.contact_birthday_cascades"]["modified"] is False
        assert "light: 10m, 0" in rows["organizer.calendar_notification_cascades"]["summary"]

    def test_city_row_carries_the_city(self):
        assert _rows(build_sections(CATALOG, VALUES))["travel.home_city_id"]["city"] == _CITY

    def test_link_rows_never_carry_their_value(self):
        row = _rows(build_sections(CATALOG, VALUES))["assistant.persona_additions"]
        assert row["value"] is None

    def test_rows_are_grouped_in_order(self):
        reminders = _section(build_sections(CATALOG, VALUES), "reminders")
        assert [g["name"] for g in reminders["groups"]][:2] == ["When am I overloaded?", "Reminders while overloaded"]

    def test_a_failing_get_leaves_only_its_rows_out(self):
        values = {**VALUES, "/travel/settings": None, "/organizer/contact-birthday-settings": None}
        sections = build_sections(CATALOG, values)
        travel, organizer, planning = (_section(sections, n) for n in ("travel", "organizer", "planning"))
        assert travel["load_error"] is True and travel["count"] == 0 and travel["groups"] == []
        assert organizer["load_error"] is True and organizer["count"] == 1
        assert planning["load_error"] is False and planning["count"] > 0

    def test_unregistered_preview_is_capped(self):
        catalog = copy.deepcopy(CATALOG)
        catalog["unregistered"] = [{"key": f"travel.checklist.k{i}", "value": "1"} for i in range(8)]
        shown, total = unregistered_preview(catalog)
        assert (len(shown), total) == (5, 8)


class TestSettingsPage:
    @pytest.fixture
    def page(self, client, mock_api):
        mock_api["get"].side_effect = _get()
        return client.get("/settings")

    def test_renders_every_section_with_nav(self, page):
        assert page.status_code == 200
        for namespace in ("planning", "reminders", "travel", "finance", "study", "organizer", "assistant"):
            assert f'id="{namespace}"' in page.text
            assert f'href="#{namespace}"' in page.text

    def test_each_widget_renders(self, page):
        html = page.text
        assert re.search(r'type="number"[^>]*min="0"[^>]*max="600"[^>]*value="100"', html, re.S)
        assert re.search(r'type="time"[^>]*value="07:00"', html)
        assert re.search(r'type="checkbox" data-control class="toggle toggle-sm" checked', html)
        assert "No meetings before 9.</textarea>" in html
        assert 'data-day="mon" checked' in html and 'data-day="sat" >' in html
        assert 'data-chip="09:00-12:00"' in html
        assert 'value="Lisbon, Portugal"' in html
        assert "Edit JSON" in html and "normal: 1h, 10m, 0" in html
        assert "1 Example Street" in html
        assert 'href="/persona"' in html

    def test_modified_badge_shows_only_when_different(self, page):
        row = re.search(r'data-key="travel.airport_buffer_min".*?data-modified class="([^"]*)"', page.text, re.S)
        assert "hidden" not in row.group(1)
        row = re.search(r'data-key="travel.home_to_airport_min".*?data-modified class="([^"]*)"', page.text, re.S)
        assert "hidden" in row.group(1)

    def test_personal_persona_text_is_never_rendered(self, page):
        assert "SECRET-PERSONA-TEXT" not in page.text
        assert 'value="Sam"' in page.text

    def test_travel_times_are_not_offered(self, page):
        assert "planning.travel_times" not in page.text

    def test_unregistered_rows_are_read_only(self, page):
        stored = page.text[page.text.index('data-stored'):]
        assert "travel.checklist.departure.passport" in stored and "core.paused_at" in stored
        assert "<input" not in stored[:stored.index("</section>")]

    def test_sidebar_has_the_settings_link(self, page):
        assert re.search(r'href="/settings" class="nav-link active"', page.text)

    def test_failing_namespace_leaves_only_its_section_empty(self, client, mock_api):
        mock_api["get"].side_effect = _get({**VALUES, "/travel/settings": None})

        html = client.get("/settings").text

        travel = html[html.index('id="travel"'):html.index('id="finance"')]
        assert "could not be loaded" in travel and "data-setting-row" not in travel
        assert 'data-key="planning.wake_time"' in html

    def test_catalog_down(self, client, mock_api):
        mock_api["get"].side_effect = _get(catalog=None)
        assert "unavailable right now" in client.get("/settings").text


class TestStoredPage:
    def test_lists_every_unregistered_key(self, client, mock_api):
        catalog = copy.deepcopy(CATALOG)
        catalog["unregistered"] = [{"key": f"travel.checklist.k{i}", "value": "1"} for i in range(8)]
        mock_api["get"].side_effect = _get(catalog=catalog)

        html = client.get("/settings/stored").text

        assert all(f"travel.checklist.k{i}" in html for i in range(8))

    def test_settings_page_links_to_it_when_capped(self, client, mock_api):
        catalog = copy.deepcopy(CATALOG)
        catalog["unregistered"] = [{"key": f"travel.checklist.k{i}", "value": "1"} for i in range(8)]
        mock_api["get"].side_effect = _get(catalog=catalog)

        html = client.get("/settings").text

        assert "See all 8" in html and 'href="/settings/stored"' in html
        assert "travel.checklist.k5" not in html


class TestPlanWrites:
    def test_fields_sharing_a_path_go_in_one_body(self):
        plan = plan_writes(CATALOG, {"travel": {"airport_buffer_min": 90, "snooze_other_events": False}})
        assert plan == {"travel": [("/travel/settings", {"airport_buffer_min": 90, "snooze_other_events": False})]}

    def test_cascades_split_into_one_put_per_entry(self):
        plan = plan_writes(CATALOG, {"organizer": {
            "profiles": {"light": ["10m", "0"], "aware": ["2d"]},
            "relationships": {"friend": ["3d"]},
        }})
        assert sorted(plan["organizer"]) == sorted([
            ("/organizer/calendar-notification-settings/light", {"offsets": ["10m", "0"]}),
            ("/organizer/calendar-notification-settings/aware", {"offsets": ["2d"]}),
            ("/organizer/contact-birthday-settings/friend", {"offsets": ["3d"]}),
        ])

    @pytest.mark.parametrize("changes", [
        {"planning": {"travel_times": []}},
        {"travel": {"home_address": "x"}},
        {"assistant": {"persona_additions": "x"}},
        {"nope": {"x": 1}},
        {"organizer": {"profiles": {"nromal": ["1h"]}}},
        {"organizer": {"profiles": ["1h"]}},
    ])
    def test_refuses_what_the_page_never_sends(self, changes):
        with pytest.raises(SaveError):
            plan_writes(CATALOG, changes)


class TestSave:
    def _put(self, fail=None):
        async def put(path, json=None):
            if fail and path.startswith(fail):
                response = httpx.Response(422, json={"detail": "airport_buffer_min: at most 600"})
                raise httpx.HTTPStatusError("422", request=httpx.Request("PUT", path), response=response)
            if path.startswith("/organizer/calendar-notification-settings/"):
                return {"profiles": {**VALUES["/organizer/calendar-notification-settings"]["profiles"],
                                     path.rsplit("/", 1)[1]: json["offsets"]}}
            return {**VALUES[path], **json}
        return put

    def test_sends_only_changed_fields_and_returns_saved_values(self, client, mock_api):
        mock_api["get"].side_effect = _get()
        mock_api["put"].side_effect = self._put()

        resp = client.post("/settings/save", json={"planning": {"wake_time": "06:30"}, "study": {"max_active_plans": 4}})

        assert resp.status_code == 200
        assert {c.args[0]: c.kwargs["json"] for c in mock_api["put"].await_args_list} == {
            "/planning/settings": {"wake_time": "06:30"}, "/study/settings": {"max_active_plans": 4},
        }
        body = resp.json()
        assert body["planning"]["ok"] is True and body["planning"]["values"]["wake_time"] == "06:30"
        assert body["study"]["values"] == {"max_active_plans": 4}

    def test_planning_never_sends_travel_times(self, client, mock_api):
        mock_api["get"].side_effect = _get()
        mock_api["put"].side_effect = self._put()

        client.post("/settings/save", json={"planning": {"work_tag": "job"}})

        assert "travel_times" not in mock_api["put"].await_args.kwargs["json"]

    def test_cascades_become_per_profile_puts(self, client, mock_api):
        mock_api["get"].side_effect = _get()
        mock_api["put"].side_effect = self._put()

        resp = client.post("/settings/save", json={"organizer": {"profiles": {"light": ["5m"], "aware": ["2d"]}}})

        assert sorted(c.args[0] for c in mock_api["put"].await_args_list) == [
            "/organizer/calendar-notification-settings/aware", "/organizer/calendar-notification-settings/light",
        ]
        assert resp.json()["organizer"]["values"]["profiles"]["aware"] == ["2d"]

    def test_a_failing_namespace_leaves_the_others_saved(self, client, mock_api):
        mock_api["get"].side_effect = _get()
        mock_api["put"].side_effect = self._put(fail="/travel")

        body = client.post("/settings/save", json={
            "travel": {"airport_buffer_min": 999}, "finance": {"cycle_start_day": 25},
        }).json()

        assert body["travel"] == {"ok": False, "error": "airport_buffer_min: at most 600"}
        assert body["finance"] == {"ok": True, "values": {"cycle_start_day": 25}}

    def test_city_change_returns_the_city(self, client, mock_api):
        mock_api["get"].side_effect = _get()
        mock_api["put"].side_effect = self._put()

        body = client.post("/settings/save", json={"travel": {"home_city_id": None}}).json()

        assert body["travel"]["values"]["home_city_id"] is None
        assert "home_city" in body["travel"]["values"]
        assert "home_address" in body["travel"]["values"]

    def test_never_returns_persona_additions(self, client, mock_api):
        mock_api["get"].side_effect = _get()
        mock_api["put"].side_effect = self._put()

        body = client.post("/settings/save", json={"assistant": {"user_name": "Alex"}}).json()

        assert body["assistant"]["values"] == {"user_name": "Alex"}

    def test_refused_change_is_a_422(self, client, mock_api):
        mock_api["get"].side_effect = _get()

        resp = client.post("/settings/save", json={"planning": {"travel_times": []}})

        assert resp.status_code == 422
        mock_api["put"].assert_not_awaited()

    def test_malformed_body_is_a_422(self, client, mock_api):
        assert client.post("/settings/save", json={"planning": 3}).status_code == 422

    def test_catalog_down_is_a_502(self, client, mock_api):
        mock_api["get"].side_effect = _get(catalog=None)
        assert client.post("/settings/save", json={"study": {"max_active_plans": 2}}).status_code == 502

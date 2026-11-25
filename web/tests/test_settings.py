import copy
import json
import re
from pathlib import Path

import httpx
import pytest

from app.shared.settings_page import SaveError, build_sections, plan_writes, read_paths, saved_values

# Generated from the backend's build_catalog().
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
    "/travel/checklist-template": {"items": [
        {"anchor": "start", "name": "currency", "title": "currency", "offset_days": -14},
        {"anchor": "end", "name": "send-photos", "title": "send photos", "offset_days": 3},
    ]},
    "/finance/settings": {"cycle_start_day": 1, "import_knn_limit": 7, "import_knn_threshold": 0.72, "import_knn_min_vote": 0.7},
    "/cs/settings": {"weak_tag_min_attempts": 3, "weak_tag_max_solve_rate": 0.85, "weak_tags_shown": 5},
    "/metrics/settings": {"trend_days": 30, "min_samples": 5},
    "/core/chat-settings": {
        "history_limit": 10, "memory_limit": 5, "memory_threshold": 0.6, "temperature": 0.5, "recall_threshold": 0.5,
        "recall_limit": 8, "memory_dedup_threshold": 0.85, "memory_importance_bump": 0.1, "intent_threshold": 0.7,
        "intent_shortlist_floor": 0.4, "intent_shortlist_k": 5,
    },
    "/briefing/settings": {
        "lookahead_days": 3, "holiday_lookahead_days": 7, "max_tasks_today": 8, "max_tasks_upcoming": 4,
        "max_events_today": 8, "max_events_upcoming": 4, "max_shopping_items": 6, "max_recurring_items": 5,
    },
    "/study/settings": {"max_active_plans": 3},
    "/language/settings": {"requested_retention": 0.9, "leech_threshold": 8, "timed_task_seconds": 300},
    "/organizer/calendar-notification-settings": {"profiles": {
        "cant_miss": ["7d", "3d", "1d", "4h", "1h", "30m", "10m", "5m", "0"], "important": ["1d", "4h", "1h", "15m", "0"],
        "normal": ["1h", "10m", "0"], "light": ["10m", "0"], "aware": ["3d", "1d"],
    }},
    "/organizer/contact-birthday-settings": {"relationships": {
        "family": ["1mo", "15d", "7d", "5d", "1d"], "relative": ["15d", "7d", "1d"], "friend": ["7d", "1d"], "other": ["3d"],
    }, "birthday_lookahead_days": 7, "birthday_dashboard_days": 30},
    "/core/weather-settings": {
        "place_id": None, "city_id": 3, "place_label": "Lisbon, Portugal",
        "choices": {"places": [{"id": 1, "label": "Office"}], "cities": [{"id": 3, "label": "Lisbon, Portugal"}]},
    },
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
        if path == "/finance/budgets/current-period":
            return {"year_month": "2026-11"}
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

    def test_place_row_covers_both_fields_and_hides_the_city_row(self):
        rows = _rows(build_sections(CATALOG, VALUES))
        assert rows["weather.place_id"]["value"] == {"place_id": None, "city_id": 3}
        assert rows["weather.place_id"]["place_label"] == "Lisbon, Portugal"
        assert "weather.city_id" not in rows

    def test_tuning_sections_and_groups_are_marked_and_last(self):
        sections = build_sections(CATALOG, VALUES)
        assert _section(sections, "chat")["advanced"] is True
        finance = _section(sections, "finance")
        assert finance["advanced"] is False
        assert [g["advanced"] for g in finance["groups"]] == [False, True]

    def test_temperature_modified_against_the_env_default(self):
        assert _rows(build_sections(CATALOG, VALUES))["chat.temperature"]["modified"] is True

    def test_markdown_row_carries_its_reference(self):
        row = _rows(build_sections(CATALOG, VALUES))["assistant.persona_additions"]
        assert (row["value"], row["reference_text"]) == ("SECRET-PERSONA-TEXT", "# Alfred")

    def test_checklist_value_keeps_only_what_its_put_takes(self):
        row = _rows(build_sections(CATALOG, VALUES))["travel.checklist"]
        assert row["value"] == [
            {"anchor": "start", "name": "currency", "offset_days": -14},
            {"anchor": "end", "name": "send-photos", "offset_days": 3},
        ]
        assert row["group"] == "Pre-trip checklist"

    def test_saved_checklist_drops_the_title_too(self):
        values = saved_values(CATALOG, "travel", [VALUES["/travel/checklist-template"]])
        assert values["items"][1] == {"anchor": "end", "name": "send-photos", "offset_days": 3}

    def test_rows_are_grouped_in_order(self):
        reminders = _section(build_sections(CATALOG, VALUES), "reminders")
        assert [g["name"] for g in reminders["groups"]][:2] == ["What is reminded", "When am I overloaded?"]

    def test_a_failing_get_leaves_only_its_rows_out(self):
        values = {**VALUES, "/travel/settings": None, "/organizer/contact-birthday-settings": None}
        sections = build_sections(CATALOG, values)
        travel, organizer, planning = (_section(sections, n) for n in ("travel", "organizer", "planning"))
        assert travel["load_error"] is True and [g["name"] for g in travel["groups"]] == ["Pre-trip checklist"]
        assert organizer["load_error"] is True and organizer["count"] == 1
        assert planning["load_error"] is False and planning["count"] > 0


class TestSettingsPage:
    @pytest.fixture
    def page(self, client, mock_api):
        mock_api["get"].side_effect = _get()
        return client.get("/settings")

    def test_renders_every_section_with_nav(self, page):
        assert page.status_code == 200
        for namespace in ("planning", "reminders", "travel", "briefing", "finance", "study", "cs", "metrics", "language",
                          "organizer", "weather", "chat", "assistant"):
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
        assert "data-markdown-edit" in html and 'id="markdown-dialog"' in html
        assert 'data-name="send-photos"' in html and "3 days after the end" in html

    def test_long_text_takes_the_full_row_width(self, page):
        row = re.search(r'data-key="planning.conventions".*?</div>\s*<div class="([^"]*)"', page.text, re.S)
        assert "w-full" in row.group(1).split() and "sm:w-auto" not in row.group(1)

    def test_place_picker_selects_the_current_place(self, page):
        assert '<option value="city:3" selected>Lisbon, Portugal</option>' in page.text
        assert '<option value="place:1" >Office</option>' in page.text
        assert "In use: Lisbon, Portugal" in page.text

    def test_tuning_rows_carry_the_flag_and_the_switch_is_there(self, page):
        assert 'id="show-tuning"' in page.text
        assert re.search(r'data-key="chat.temperature"[^>]*data-advanced', page.text, re.S)
        assert re.search(r'<section id="chat"[^>]*data-advanced', page.text)
        assert not re.search(r'data-key="travel.airport_buffer_min"[^>]*data-advanced', page.text.split('data-value=')[0])

    def test_modified_badge_shows_only_when_different(self, page):
        row = re.search(r'data-key="travel.airport_buffer_min".*?data-modified class="([^"]*)"', page.text, re.S)
        assert "hidden" not in row.group(1)
        row = re.search(r'data-key="travel.home_to_airport_min".*?data-modified class="([^"]*)"', page.text, re.S)
        assert "hidden" in row.group(1)

    def test_finance_shows_the_current_cycle(self, page):
        finance = page.text[page.text.index('id="finance"'):page.text.index('id="study"')]
        assert "Current cycle: 2026-11" in finance

    def test_persona_additions_and_base_persona_are_in_the_editor(self, page):
        row = page.text[page.text.index('data-key="assistant.persona_additions"'):]
        assert re.search(r'<textarea data-control hidden maxlength="20000"[^>]*>SECRET-PERSONA-TEXT</textarea>', row)
        assert re.search(r'<pre hidden data-reference data-reference-label="Base persona[^"]*"># Alfred</pre>', row)
        assert "19 characters" in row
        assert 'value="Sam"' in page.text

    def test_checklist_items_are_grouped_by_anchor(self, page):
        start = page.text[page.text.index('data-checklist="start"'):page.text.index('data-checklist="end"')]
        assert 'data-name="currency"' in start and 'value="-14"' in start and "14 days before the start" in start
        assert 'data-name="send-photos"' not in start

    def test_travel_times_are_not_offered(self, page):
        assert "planning.travel_times" not in page.text

    def test_no_stored_values_card_and_no_persona_page_link(self, page):
        assert "data-stored" not in page.text and "Other stored settings" not in page.text
        assert 'href="/persona"' not in page.text

    def test_sidebar_has_the_settings_link(self, page):
        assert re.search(r'href="/settings" class="nav-link active"', page.text)

    def test_failing_namespace_get_leaves_out_only_its_rows(self, client, mock_api):
        mock_api["get"].side_effect = _get({**VALUES, "/travel/settings": None})

        html = client.get("/settings").text

        travel = html[html.index('id="travel"'):html.index('id="briefing"')]
        assert "could not be loaded" in travel and 'data-key="travel.airport_buffer_min"' not in travel
        assert 'data-key="travel.checklist"' in travel
        assert 'data-key="planning.wake_time"' in html

    def test_catalog_down(self, client, mock_api):
        mock_api["get"].side_effect = _get(catalog=None)
        assert "unavailable right now" in client.get("/settings").text


class TestRemovedPages:
    @pytest.mark.parametrize("path", ["/settings/stored", "/persona"])
    def test_are_gone(self, client, mock_api, path):
        assert client.get(path).status_code == 404


class TestPlanWrites:
    def test_fields_sharing_a_path_go_in_one_body(self):
        plan = plan_writes(CATALOG, {"travel": {"airport_buffer_min": 90, "snooze_other_events": False}})
        assert plan == {"travel": [("/travel/settings", {"airport_buffer_min": 90, "snooze_other_events": False})]}

    def test_checklist_is_written_whole(self):
        items = [{"anchor": "start", "name": "currency", "offset_days": -10}]
        plan = plan_writes(CATALOG, {"travel": {"items": items, "airport_buffer_min": 90}})
        assert sorted(plan["travel"]) == [
            ("/travel/checklist-template", {"items": items}), ("/travel/settings", {"airport_buffer_min": 90}),
        ]

    def test_persona_additions_are_sent_to_the_assistant_settings(self):
        plan = plan_writes(CATALOG, {"assistant": {"persona_additions": "More."}})
        assert plan == {"assistant": [("/core/assistant-settings", {"persona_additions": "More."})]}

    def test_place_writes_both_fields(self):
        plan = plan_writes(CATALOG, {"weather": {"place_id": {"place_id": 1, "city_id": None}}})
        assert plan == {"weather": [("/core/weather-settings", {"place_id": 1, "city_id": None})]}

    @pytest.mark.parametrize("value", [{"place_id": 1, "nope": 2}, 5])
    def test_place_refuses_other_shapes(self, value):
        with pytest.raises(SaveError):
            plan_writes(CATALOG, {"weather": {"place_id": value}})

    def test_hidden_field_is_never_sent_alone(self):
        with pytest.raises(SaveError):
            plan_writes(CATALOG, {"weather": {"city_id": 3}})

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
        assert body["finance"]["ok"] is True and body["finance"]["values"]["cycle_start_day"] == 25

    def test_city_change_returns_the_city(self, client, mock_api):
        mock_api["get"].side_effect = _get()
        mock_api["put"].side_effect = self._put()

        body = client.post("/settings/save", json={"travel": {"home_city_id": None}}).json()

        assert body["travel"]["values"]["home_city_id"] is None
        assert "home_city" in body["travel"]["values"]
        assert "home_address" in body["travel"]["values"]

    def test_place_save_returns_the_place_and_its_label(self, client, mock_api):
        mock_api["get"].side_effect = _get()
        mock_api["put"].side_effect = self._put()

        body = client.post("/settings/save", json={"weather": {"place_id": {"place_id": 1, "city_id": None}}}).json()

        assert mock_api["put"].await_args.kwargs["json"] == {"place_id": 1, "city_id": None}
        assert body["weather"]["values"]["place_id"] == {"place_id": 1, "city_id": None}
        assert "place_label" in body["weather"]["values"]

    def test_returns_the_saved_persona_additions_but_not_the_base(self, client, mock_api):
        mock_api["get"].side_effect = _get()
        mock_api["put"].side_effect = self._put()

        body = client.post("/settings/save", json={"assistant": {"persona_additions": "More."}}).json()

        assert body["assistant"]["values"] == {"user_name": "Sam", "persona_additions": "More."}

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

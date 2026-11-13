from datetime import date, datetime
from zoneinfo import ZoneInfo

import httpx
import pytest

from app.shared import dashboard as cards

NOW = datetime(2026, 11, 13, 12, 0, tzinfo=ZoneInfo("Europe/Lisbon"))
TODAY = NOW.date()


def _task(title="Pay rent", deadline=None, urgency="NORMAL", **kw):
    return {"id": 1, "title": title, "deadline": deadline, "urgency": urgency, "priority": "MEDIUM", "tags": [], **kw}


def _block(start, end, title, **kw):
    return {"start": f"2026-11-13T{start}:00+00:00", "end": f"2026-11-13T{end}:00+00:00", "kind": "task", "title": title, **kw}


def _plan(items, plan_date="2026-11-13", archived_at=None):
    return {"id": 1, "plan_date": plan_date, "version": 1, "items": items, "archived_at": archived_at}


class TestTaskAlerts:
    def test_counts_overdue_and_urgent(self):
        tasks = [
            _task(deadline="2026-11-12T09:00:00+00:00"),
            _task(deadline="2026-11-14T09:00:00+00:00"),
            _task(urgency="URGENT"),
            _task(),
        ]

        assert cards.task_alerts(tasks, NOW) == {"overdue": 1, "urgent": 1}

    def test_naive_deadline_is_read_in_the_local_zone(self):
        assert cards.task_alerts([_task(deadline="2026-11-13T11:59:00")], NOW)["overdue"] == 1
        assert cards.task_alerts([_task(deadline="2026-11-13T12:01:00")], NOW)["overdue"] == 0

    def test_task_done_in_its_cycle_is_not_overdue(self):
        done = _task(deadline="2026-11-12T09:00:00+00:00", is_done_in_cycle=True)

        assert cards.task_alerts([done], NOW)["overdue"] == 0


class TestPlanCard:
    def test_returns_blocks_from_the_current_one_onward(self):
        plan = _plan([_block("08:00", "09:00", "Gym", done=True), _block("11:30", "12:30", "Write report"), _block("14:00", "15:00", "Call")])

        card = cards.plan_card([plan], TODAY, "12:00")

        assert [b["title"] for b in card["blocks"]] == ["Write report", "Call"]
        assert card["blocks"][0]["current"] is True and card["blocks"][1]["current"] is False
        assert (card["total"], card["done"], card["finished"]) == (3, 1, False)

    def test_caps_blocks_and_reports_the_rest(self):
        plan = _plan([_block(f"{h:02d}:00", f"{h:02d}:30", f"Block {h}") for h in range(13, 20)])

        card = cards.plan_card([plan], TODAY, "12:00")

        assert len(card["blocks"]) == cards.CARD_CAP and card["more"] == 2

    def test_finished_when_every_block_has_ended(self):
        card = cards.plan_card([_plan([_block("08:00", "09:00", "Gym", done=True)])], TODAY, "12:00")

        assert card["finished"] is True and card["blocks"] == []

    def test_ignores_other_days_and_archived_versions(self):
        plans = [_plan([_block("13:00", "14:00", "x")], plan_date="2026-11-14"),
                 _plan([_block("13:00", "14:00", "y")], archived_at="2026-11-13T08:00:00")]

        assert cards.plan_card(plans, TODAY, "12:00") is None

    def test_none_without_plans(self):
        assert cards.plan_card(None, TODAY, "12:00") is None


class TestTripCard:
    def _trip(self, start, end, id=1):
        return {"id": id, "name": "Lisbon", "start_date": start, "end_date": end}

    def test_card_counts_other_calendar_events_like_the_warnings_page(self):
        card = cards.trip_card([self._trip("2026-12-17", "2026-12-24")], {"warnings": [{}, {}]}, TODAY, [{}, {}, {}])

        assert card["warnings"] == 5

    def test_upcoming_trip_counts_days_and_warnings(self):
        card = cards.trip_card([self._trip("2026-12-17", "2026-12-24")], {"warnings": [{}, {}]}, TODAY)

        assert (card["ongoing"], card["days_until"], card["warnings"]) == (False, 34, 2)

    def test_ongoing_trip_reports_the_day(self):
        card = cards.trip_card([self._trip("2026-11-12", "2026-11-15")], None, TODAY)

        assert (card["ongoing"], card["day"], card["days"], card["warnings"]) == (True, 2, 4, 0)

    def test_picks_the_nearest_trip(self):
        card = cards.trip_card([self._trip("2027-01-10", "2027-01-12", id=2), self._trip("2026-12-17", "2026-12-24", id=1)], None, TODAY)

        assert card["id"] == 1

    def test_none_without_trips(self):
        assert cards.trip_card([], None, TODAY) is None


class TestSparkline:
    def test_scales_values_into_the_box(self):
        points = cards.sparkline([0, 10]).split()

        assert points == ["0.0,22.0", "100.0,2.0"]

    def test_flat_series_sits_mid_height(self):
        assert cards.sparkline([3, 3, 3]).split() == ["0.0,12.0", "50.0,12.0", "100.0,12.0"]

    def test_needs_two_values(self):
        assert cards.sparkline([5]) == ""


class TestMetricCard:
    def test_count_series_uses_entries_per_day_with_zero_for_gaps(self):
        series = {"name": "coffee", "kind": "count", "unit": None}
        daily = {"points": [{"date": "2026-11-13", "n": 3, "total": None}, {"date": "2026-11-12", "n": 2, "total": None}]}

        card = cards.metric_card(series, daily, TODAY)

        assert (card["today"], card["week"]) == (3.0, 5.0)

    def test_value_series_uses_daily_total(self):
        series = {"name": "weight", "kind": "value", "unit": "kg"}
        daily = {"points": [{"date": "2026-11-13", "n": 1, "total": 71.5}]}

        assert cards.metric_card(series, daily, TODAY)["today"] == 71.5

    def test_missing_daily_gives_zeros(self):
        card = cards.metric_card({"name": "x", "kind": "count", "unit": None}, None, TODAY)

        assert card["today"] == 0 and card["week"] == 0


class TestPickSeries:
    def test_skips_archived_and_empty_and_keeps_the_most_used(self):
        series = [
            {"name": "a", "is_archived": False, "entry_count": 2},
            {"name": "b", "is_archived": True, "entry_count": 99},
            {"name": "c", "is_archived": False, "entry_count": 0},
            {"name": "d", "is_archived": False, "entry_count": 9},
        ]

        assert [s["name"] for s in cards.pick_series(series)] == ["d", "a"]


class TestBudgetRows:
    def test_ranks_by_how_close_to_the_limit_and_skips_unlimited(self):
        statuses = [
            {"category_name": "Food", "limit_amount": "400.00", "spent": "380.00"},
            {"category_name": "Fun", "limit_amount": "100.00", "spent": "130.00"},
            {"category_name": "Misc", "limit_amount": None, "spent": "50.00"},
            {"category_name": "Gym", "limit_amount": "50.00", "spent": "5.00"},
            {"category_name": "Car", "limit_amount": "200.00", "spent": "100.00"},
        ]

        rows = cards.budget_rows(statuses)

        assert [r["name"] for r in rows] == ["Fun", "Food", "Car"]
        assert rows[0]["ratio"] == pytest.approx(1.3)


class TestUpcomingBirthdays:
    def test_lists_the_next_30_days_soonest_first(self):
        contacts = [
            {"name": "Ana", "birthday": "1990-11-20"},
            {"name": "Bruno", "birthday": "1985-11-13"},
            {"name": "Carla", "birthday": "2000-06-01"},
            {"name": "Rui", "birthday": "1980-12-13"},
            {"name": "Dora", "birthday": "1980-12-14"},
        ]

        found = cards.upcoming_birthdays(contacts, TODAY)

        assert [(b["name"], b["days_until"]) for b in found] == [("Bruno", 0), ("Ana", 7), ("Rui", 30)]

    def test_wraps_into_next_year_and_skips_self_and_missing(self):
        contacts = [
            {"name": "Eva", "birthday": "1990-01-02"},
            {"name": "Me", "birthday": "1990-11-14", "is_self": True},
            {"name": "NoDate", "birthday": None},
        ]

        found = cards.upcoming_birthdays(contacts, date(2026, 12, 20))

        assert [(b["name"], b["date"]) for b in found] == [("Eva", date(2027, 1, 2))]

    def test_leap_day_birthday_falls_on_march_first_in_common_years(self):
        found = cards.upcoming_birthdays([{"name": "Leo", "birthday": "2000-02-29"}], date(2027, 2, 20))

        assert found[0]["date"] == date(2027, 3, 1)


class TestBriefingType:
    def test_morning_during_the_day_and_evening_from_the_digest_time(self):
        assert cards.briefing_type(NOW) == "morning"
        assert cards.briefing_type(NOW.replace(hour=21, minute=29)) == "morning"
        assert cards.briefing_type(NOW.replace(hour=21, minute=30)) == "evening"
        assert cards.briefing_type(NOW.replace(hour=23, minute=59)) == "evening"


class TestLanguageCard:
    def test_joins_tracks_with_todays_progress_and_skips_tracks_without_any(self):
        tracks = [{"id": 1, "name": "Spanish"}, {"id": 2, "name": "French"}]
        progress = [{"track_id": 1, "daily_quota": 5, "completed_today": 5, "quota_met": True}]

        assert cards.language_card(tracks, progress) == [
            {"name": "Spanish", "completed_today": 5, "daily_quota": 5, "quota_met": True}]

    def test_no_data(self):
        assert cards.language_card(None, None) == []


class TestStudyCard:
    def test_progress_and_next_open_item(self):
        overview = {"active": [{"title": "Graphs", "items": [
            {"description": "BFS", "is_done": True}, {"description": "DFS", "is_done": False}, {"description": "Dijkstra", "is_done": False}]}]}

        assert cards.study_card(overview) == [{"title": "Graphs", "done": 1, "total": 3, "next": "DFS"}]

    def test_finished_plan_has_no_next_item(self):
        overview = {"active": [{"title": "Done", "items": [{"description": "x", "is_done": True}]}]}

        assert cards.study_card(overview)[0]["next"] is None

    def test_no_overview(self):
        assert cards.study_card(None) == []


def _backend(overrides=None):
    """A fake backend: every dashboard endpoint answers with a small valid payload unless overridden."""
    data = {
        "/organizer/tasks": [_task("Pay rent", deadline="2026-11-12T09:00:00+00:00", urgency="URGENT")],
        "/organizer/shopping": [{"name": "Milk", "priority": "need", "category": "dairy"}],
        "/organizer/calendar-events": [],
        "/finance/transactions/report": {"total": 1234.5},
        "/planning/saved": [_plan([_block("13:00", "14:00", "Deep work")])],
        "/finance/budgets/status": [{"category_name": "Food", "limit_amount": "400", "spent": "380"}],
        "/organizer/contacts": [{"name": "Bruno", "birthday": "1985-11-14"}],
        "/study/plans/overview": {"active": [{"title": "Graphs", "items": [{"description": "BFS", "is_done": False}]}]},
        "/briefing/history": [{"date": "2026-11-13", "type": "morning", "text": "Good morning David"}],
        "/metrics/series": [{"name": "coffee", "kind": "count", "unit": None, "is_archived": False, "entry_count": 4}],
        "/metrics/series/coffee/daily": {"points": [{"date": "2026-11-13", "n": 2, "total": None}]},
        "/travel/trips": [{"id": 7, "name": "Lisbon", "start_date": "2026-12-17", "end_date": "2026-12-24"}],
        "/travel/trips/7": {"warnings": [{"kind": "no_return_leg"}]},
        "/travel/trips/7/other-events": [],
        "/language/tracks": [{"id": 1, "name": "Spanish"}, {"id": 2, "name": "Paused one"}],
        "/language/sessions/daily-progress": [{"track_id": 1, "track_code": "es", "daily_quota": 5, "completed_today": 2, "quota_met": False}],
        "/briefing/morning": {
            "weather": {"temperature_max_c": 24.4, "temperature_min_c": 15.1, "feels_like_max_c": 23.0,
                        "precipitation_probability": 10, "wind_speed_max_kmh": 12.3,
                        "description": "Partly cloudy", "advice": ["Bring a light jacket"]},
            "holidays": [{"name": "Christmas Day", "local_name": "Natal", "days_until": 3}],
        },
        **(overrides or {}),
    }

    def fake_get(path, params=None):
        value = data[path]
        if isinstance(value, Exception):
            raise value
        return value

    return fake_get


@pytest.fixture
def noon(monkeypatch):
    monkeypatch.setattr("app.routes.dashboard.local_now", lambda: NOW)
    monkeypatch.setattr("app.routes.dashboard.local_today", lambda: TODAY)


def _history_by_type(morning, evening):
    def history(params):
        rows = {"morning": morning, "evening": evening}[params["type"]]
        return [rows] if rows else []

    return history


@pytest.fixture
def night(monkeypatch):
    late = NOW.replace(hour=22, minute=0)
    monkeypatch.setattr("app.routes.dashboard.local_now", lambda: late)
    monkeypatch.setattr("app.routes.dashboard.local_today", lambda: TODAY)


@pytest.mark.usefixtures("noon")
class TestDashboardPage:
    def test_renders_every_card(self, client, mock_api):
        mock_api["get"].side_effect = _backend()

        text = client.get("/").text

        assert "1</strong> overdue" in text and "1</strong> urgent" in text
        assert "Deep work" in text and "13:00–14:00" in text
        assert "Lisbon" in text and "In 34 days" in text and "1 warning" in text
        assert "Food" in text and "€380 / €400" in text
        assert "Bruno" in text and "Tomorrow" in text
        assert "Graphs" in text and "Next: BFS" in text
        assert "coffee" in text and "Good morning David" in text
        assert "Spanish" in text and "2/5" in text and "Paused one" not in text
        assert "Partly cloudy" in text and "Bring a light jacket" in text
        assert "Natal" in text and "in 3 days" in text
        assert "ti-cake" in text and "ti-cloud" in text and "ti-flag" in text
        assert "glance" not in text

    def test_one_failing_module_does_not_blank_the_page(self, client, mock_api):
        mock_api["get"].side_effect = _backend({
            "/planning/saved": httpx.ConnectError("down"),
            "/travel/trips": httpx.ConnectError("down"),
            "/metrics/series": httpx.ConnectError("down"),
        })

        resp = client.get("/")

        assert resp.status_code == 200
        assert "No plan for today" in resp.text and "No upcoming trips" in resp.text
        assert "Pay rent" in resp.text

    def test_failing_morning_briefing_only_empties_weather_and_holidays(self, client, mock_api):
        mock_api["get"].side_effect = _backend({"/briefing/morning": httpx.ConnectError("down")})

        resp = client.get("/")

        assert resp.status_code == 200
        assert "Weather unavailable" in resp.text and "No holidays in the next 7 days" in resp.text
        assert "Pay rent" in resp.text

    def test_quiet_dashboard_has_no_alert_strip(self, client, mock_api):
        mock_api["get"].side_effect = _backend({"/organizer/tasks": [_task()]})

        assert "overdue" not in client.get("/").text



class TestBriefingCardByTime:
    MORNING = {"date": "2026-11-13", "type": "morning", "text": "Good morning David"}
    EVENING = {"date": "2026-11-13", "type": "evening", "text": "Wins of the day"}

    def _get(self, client, mock_api, morning, evening):
        history = _history_by_type(morning, evening)
        backend = _backend()
        mock_api["get"].side_effect = lambda path, params=None: history(params) if path == "/briefing/history" else backend(path, params)
        return client.get("/").text

    @pytest.mark.usefixtures("noon")
    def test_daytime_shows_only_the_morning_briefing(self, client, mock_api):
        text = self._get(client, mock_api, self.MORNING, self.EVENING)

        assert "Good morning David" in text and "Morning briefing" in text
        assert "Wins of the day" not in text

    @pytest.mark.usefixtures("night")
    def test_night_shows_only_the_evening_digest(self, client, mock_api):
        text = self._get(client, mock_api, self.MORNING, self.EVENING)

        assert "Wins of the day" in text and "Evening digest" in text and "/briefing/evening" in text
        assert "Good morning David" not in text

    @pytest.mark.usefixtures("night")
    def test_night_falls_back_to_morning_until_tonights_digest_exists(self, client, mock_api):
        stale = {**self.EVENING, "date": "2026-11-12"}

        text = self._get(client, mock_api, self.MORNING, stale)

        assert "Good morning David" in text and "Morning briefing" in text
        assert "Wins of the day" not in text

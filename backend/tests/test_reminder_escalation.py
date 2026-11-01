from datetime import datetime, timedelta

from app.features.core.reminders import escalation
from app.features.core.reminders.schemas import ReminderSettingsRead


def _settings(**overrides) -> ReminderSettingsRead:
    values = {
        "overload_overdue_threshold": 5, "overload_urgent_threshold": 4, "overload_max_listed": 5,
        "overload_urgent_interval_hours": 4, "overdue_grace_hours_high": 0,
        "overdue_grace_hours_medium": 48, "overdue_grace_hours_low": 168,
        "undated_escalation_days_high": 7, "undated_escalation_days_medium": 21,
        "undated_escalation_days_low": 45, "urgency_reset_days": 7, "catchup_tasks_per_day": 3, "catchup_stale_days": 30,
        "catchup_missed_habit_threshold": 3,
    }
    return ReminderSettingsRead(**{**values, **overrides})


class TestOverdueGrace:
    def test_grace_grows_as_priority_drops(self):
        settings = _settings()
        high = escalation.overdue_grace("HIGH", settings)
        medium = escalation.overdue_grace("MEDIUM", settings)
        low = escalation.overdue_grace("LOW", settings)
        assert high == timedelta(0)
        assert high < medium < low

    def test_reads_configured_values(self):
        settings = _settings(overdue_grace_hours_medium=12)
        assert escalation.overdue_grace("MEDIUM", settings) == timedelta(hours=12)

    def test_unknown_priority_gets_the_lowest_priority_grace(self):
        assert escalation.overdue_grace("???", _settings()) == timedelta(hours=168)


class TestUndatedEscalationAge:
    def test_age_grows_as_priority_drops(self):
        settings = _settings()
        high = escalation.undated_escalation_age("HIGH", settings)
        medium = escalation.undated_escalation_age("MEDIUM", settings)
        low = escalation.undated_escalation_age("LOW", settings)
        assert high < medium < low

    def test_reads_configured_values(self):
        settings = _settings(undated_escalation_days_high=3)
        assert escalation.undated_escalation_age("HIGH", settings) == timedelta(days=3)

    def test_zero_days_means_never(self):
        settings = _settings(undated_escalation_days_low=0)
        assert escalation.undated_escalation_age("LOW", settings) is None


class TestIsStaleUndated:
    NOW = datetime(2026, 11, 1, 12, 0)

    def test_old_task_is_stale(self):
        assert escalation.is_stale_undated(self.NOW - timedelta(days=50), self.NOW, "LOW", _settings())

    def test_young_task_is_not_stale(self):
        assert not escalation.is_stale_undated(self.NOW - timedelta(days=10), self.NOW, "LOW", _settings())

    def test_never_setting_ignores_age(self):
        settings = _settings(undated_escalation_days_low=0)
        assert not escalation.is_stale_undated(self.NOW - timedelta(days=1000), self.NOW, "LOW", settings)


class TestTaskDedupTtl:
    def test_overload_interval_is_configurable(self):
        settings = _settings(overload_urgent_interval_hours=6)
        ttl = escalation.task_dedup_ttl("URGENT", "HIGH", True, settings)
        assert ttl == timedelta(hours=6) - timedelta(minutes=10)

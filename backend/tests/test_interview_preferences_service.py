from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.features.organizer.interviews.preferences.schemas import InterviewPreferencesUpdate
from app.features.organizer.interviews.preferences.service import InterviewPreferencesService


def _make_preferences_orm(**kwargs):
    orm = MagicMock()
    orm.id = kwargs.get("id", 1)
    orm.work_regimes = kwargs.get("work_regimes", [])
    orm.target_office_days_per_month = kwargs.get("target_office_days_per_month", None)
    orm.salary_min = kwargs.get("salary_min", None)
    orm.salary_max = kwargs.get("salary_max", None)
    orm.salary_currency = kwargs.get("salary_currency", None)
    orm.locations = kwargs.get("locations", [])
    orm.tech_stack = kwargs.get("tech_stack", [])
    orm.roles = kwargs.get("roles", [])
    orm.career_objectives = kwargs.get("career_objectives", None)
    orm.created_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
    orm.updated_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return orm


@pytest.fixture
def service():
    svc = InterviewPreferencesService(session=AsyncMock())
    svc._repo = AsyncMock()
    return svc


class TestGetPreferences:
    async def test_returns_preferences_from_repo(self, service):
        service._repo.get_preferences.return_value = _make_preferences_orm(
            work_regimes=["remote", "hybrid"], tech_stack=["Java", "Python"]
        )
        result = await service.get_preferences()
        service._repo.get_preferences.assert_called_once()
        assert result.work_regimes == ["remote", "hybrid"]
        assert result.tech_stack == ["Java", "Python"]


class TestUpdatePreferences:
    async def test_delegates_to_repo(self, service):
        service._repo.update_preferences.return_value = _make_preferences_orm(
            work_regimes=["remote"], salary_min=80000, salary_max=100000, salary_currency="EUR"
        )
        data = InterviewPreferencesUpdate(work_regimes=["remote"], salary_min=80000, salary_max=100000, salary_currency="EUR")
        result = await service.update_preferences(data)
        service._repo.update_preferences.assert_called_once_with(data)
        assert result.work_regimes == ["remote"]
        assert result.salary_min == 80000

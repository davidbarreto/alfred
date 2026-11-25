"""Tuning settings (chat.*, cs.*, metrics.*): defaults are the old constants, env values are fallbacks, routes work."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.features.core.chat_settings.schemas import ChatSettingsUpdate
from app.features.core.chat_settings.service import ChatSettingsService
from app.features.cs.settings.schemas import CsSettingsUpdate
from app.features.cs.settings.service import CsSettingsService
from app.features.metrics.settings.schemas import MetricsSettingsUpdate
from app.features.metrics.settings.service import MetricsSettingsService

AUTH = {"Authorization": "Bearer test-api-token"}


def _service(cls, stored=None):
    svc = cls(AsyncMock())
    svc._settings = AsyncMock()
    svc._settings.get_value.side_effect = lambda key: (stored or {}).get(key)
    return svc


class TestChatSettings:
    @pytest.fixture(autouse=True)
    def _env(self):
        env = MagicMock(llm_chat_temperature=0.4, intent_threshold=0.72, intent_shortlist_floor=0.45, intent_shortlist_k=6)
        with patch("app.features.core.chat_settings.service.get_settings", return_value=env):
            yield

    async def test_defaults_are_the_old_constants_and_env(self):
        s = await _service(ChatSettingsService).get()
        assert (s.history_limit, s.memory_limit, s.memory_threshold, s.recall_threshold, s.recall_limit) == (10, 5, 0.6, 0.5, 8)
        assert (s.memory_dedup_threshold, s.memory_importance_bump) == (0.85, 0.1)
        assert (s.temperature, s.intent_threshold, s.intent_shortlist_floor, s.intent_shortlist_k) == (0.4, 0.72, 0.45, 6)

    async def test_portal_value_wins_over_env(self):
        s = await _service(ChatSettingsService, {"chat.temperature": "0.9", "chat.intent_shortlist_k": "3"}).get()
        assert (s.temperature, s.intent_shortlist_k) == (0.9, 3)

    async def test_update_stores_only_the_given_fields(self):
        svc = _service(ChatSettingsService)
        await svc.update(ChatSettingsUpdate(memory_threshold=0.65))
        svc._settings.set_value.assert_awaited_once_with("chat.memory_threshold", "0.65")

    def test_out_of_range(self):
        with pytest.raises(ValidationError):
            ChatSettingsUpdate(temperature=3)


class TestCsAndMetricsSettings:
    async def test_cs_defaults_are_the_old_constants(self):
        s = await _service(CsSettingsService).get()
        assert (s.weak_tag_min_attempts, s.weak_tag_max_solve_rate, s.weak_tags_shown) == (3, 0.85, 5)

    async def test_metrics_defaults_are_the_old_constants(self):
        s = await _service(MetricsSettingsService).get()
        assert (s.trend_days, s.min_samples) == (30, 5)

    async def test_updates_are_namespaced(self):
        cs, metrics = _service(CsSettingsService), _service(MetricsSettingsService)
        await cs.update(CsSettingsUpdate(weak_tags_shown=3))
        await metrics.update(MetricsSettingsUpdate(trend_days=14))
        cs._settings.set_value.assert_awaited_once_with("cs.weak_tags_shown", "3")
        metrics._settings.set_value.assert_awaited_once_with("metrics.trend_days", "14")


class TestRoutes:
    @pytest.mark.parametrize("path,dep,field", [
        ("/core/chat-settings", "get_chat_settings_service", "history_limit"),
        ("/cs/settings", "get_cs_settings_service", "weak_tags_shown"),
        ("/metrics/settings", "get_metrics_settings_service", "trend_days"),
    ])
    def test_get_put_and_validation(self, path, dep, field):
        import app.dependencies as deps
        from app.main import app

        service = AsyncMock()
        service.get.return_value = {field: 7}
        service.update.return_value = {field: 8}
        app.dependency_overrides[getattr(deps, dep)] = lambda: service
        try:
            client = TestClient(app)
            assert client.get(path).status_code == 403
            service.get.return_value = None
            put = client.put(path, json={field: 9999}, headers=AUTH)
            assert put.status_code == 422
            service.update.assert_not_awaited()
        finally:
            app.dependency_overrides.clear()

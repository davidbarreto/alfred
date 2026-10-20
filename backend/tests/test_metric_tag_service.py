from unittest.mock import AsyncMock

import pytest
from sqlalchemy.exc import IntegrityError

from app.features.metrics.tags.schemas import MetricTagUpdate, normalize_tags
from app.features.metrics.tags.service import MetricTagInUseError, MetricTagNameTakenError, MetricTagService
from app.features.metrics.tags.tables import MetricTag


@pytest.fixture
def service():
    svc = MetricTagService(AsyncMock())
    svc._repo = AsyncMock()
    return svc


class TestNormalizeTags:
    def test_dedupes_case_insensitively_first_spelling_wins(self):
        assert normalize_tags([" Bus", "bus", "", "Metro"]) == ["Bus", "Metro"]

    def test_none_stays_none(self):
        assert normalize_tags(None) is None

    def test_overlong_tag_is_rejected(self):
        with pytest.raises(ValueError):
            normalize_tags(["x" * 101])


class TestRename:
    async def test_name_clash_is_rejected(self, service):
        service._repo.get_tag_by_name.return_value = MetricTag(id=2, name="bus")
        with pytest.raises(MetricTagNameTakenError):
            await service.rename_tag(1, MetricTagUpdate(name="Bus"))

    async def test_changing_only_the_case_of_its_own_name_is_allowed(self, service):
        service._repo.get_tag_by_name.return_value = MetricTag(id=1, name="bus")
        service._repo.rename_tag.return_value = MetricTag(id=1, name="Bus")
        assert (await service.rename_tag(1, MetricTagUpdate(name="Bus"))).name == "Bus"

    async def test_unique_index_race_is_reported_as_name_taken(self, service):
        service._repo.get_tag_by_name.return_value = None
        service._repo.rename_tag.side_effect = IntegrityError("x", {}, Exception())
        with pytest.raises(MetricTagNameTakenError):
            await service.rename_tag(1, MetricTagUpdate(name="bus"))

    async def test_unknown_tag(self, service):
        service._repo.get_tag_by_name.return_value = None
        service._repo.rename_tag.return_value = None
        assert await service.rename_tag(1, MetricTagUpdate(name="x")) is None


class TestDelete:
    async def test_tag_in_use_is_kept(self, service):
        service._repo.count_usage.return_value = 5
        with pytest.raises(MetricTagInUseError) as exc:
            await service.delete_tag(1)
        assert exc.value.entry_count == 5
        service._repo.delete_tag.assert_not_awaited()

    async def test_unused_tag_is_deleted(self, service):
        service._repo.count_usage.return_value = 0
        service._repo.delete_tag.return_value = True
        assert await service.delete_tag(1) is True

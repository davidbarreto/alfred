import pytest
from datetime import datetime
from app.shared.domain import DomainRecord


class TestDomainRecord:
    def test_default_id_is_none(self):
        record = DomainRecord()
        assert record.id is None

    def test_id_can_be_set(self):
        record = DomainRecord(id="abc-123")
        assert record.id == "abc-123"

    def test_to_record_raises_not_implemented(self):
        record = DomainRecord()
        with pytest.raises(NotImplementedError):
            record.to_record()

    def test_from_record_raises_not_implemented(self):
        with pytest.raises(NotImplementedError):
            DomainRecord.from_record({})

    def test_now_iso_returns_string(self):
        result = DomainRecord._now_iso()
        assert isinstance(result, str)

    def test_now_iso_valid_iso_format(self):
        result = DomainRecord._now_iso()
        # Should parse as ISO datetime without error
        dt = datetime.fromisoformat(result)
        assert dt is not None

    def test_now_iso_reflects_current_time(self):
        from freezegun import freeze_time
        with freeze_time("2024-05-20 10:00:00"):
            result = DomainRecord._now_iso()
            assert result.startswith("2024-05-20")

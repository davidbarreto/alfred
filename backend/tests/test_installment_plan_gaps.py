from datetime import date
from decimal import Decimal

from app.features.finance.installment_plans.gaps import CapturedInstallment, build_slots, parse_position


def _cap(position: int, day: date) -> CapturedInstallment:
    return CapturedInstallment(position, 100 + position, day, Decimal("-20.00"))


class TestParsePosition:
    def test_reads_trailing_plan_position(self):
        assert parse_position("COMPRA 4681 SAMPLE SHOP (00014/3)") == 3

    def test_none_without_position(self):
        assert parse_position("COMPRA 4681 SAMPLE SHOP") is None
        assert parse_position(None) is None

    def test_ignores_position_not_at_the_end(self):
        assert parse_position("SHOP (00014/3) EXTRA") is None


class TestBuildSlots:
    def test_gap_between_captured_is_missing_with_expected_month(self):
        captured = [_cap(1, date(2024, 11, 29)), _cap(2, date(2024, 12, 31)), _cap(4, date(2025, 2, 28))]
        slots = build_slots(4, captured, today=date(2025, 3, 10))
        assert [s.status for s in slots] == ["captured", "captured", "missing", "captured"]
        assert slots[2].expected_month == "2025-01"
        assert slots[2].transaction_id is None

    def test_captured_slot_carries_transaction_details(self):
        slots = build_slots(2, [_cap(1, date(2025, 1, 31))], today=date(2025, 1, 31))
        assert slots[0].transaction_date == date(2025, 1, 31)
        assert slots[0].amount == Decimal("-20.00")
        assert slots[0].transaction_id == 101

    def test_trailing_slots_overdue_once_their_month_is_over(self):
        slots = build_slots(4, [_cap(1, date(2025, 1, 31))], today=date(2025, 3, 5))
        assert [s.status for s in slots] == ["captured", "overdue", "upcoming", "upcoming"]
        assert [s.expected_month for s in slots] == ["2025-01", "2025-02", "2025-03", "2025-04"]

    def test_expected_month_crosses_year_boundary(self):
        slots = build_slots(3, [_cap(1, date(2024, 12, 31))], today=date(2024, 12, 31))
        assert [s.expected_month for s in slots] == ["2024-12", "2025-01", "2025-02"]

    def test_anchors_on_nearest_captured_position(self):
        # Position 3 is closest to 4 (not 1), so a skipped month in between doesn't skew it.
        captured = [_cap(1, date(2025, 1, 31)), _cap(3, date(2025, 4, 30)), _cap(5, date(2025, 6, 30))]
        slots = build_slots(5, captured, today=date(2025, 7, 1))
        assert slots[3].status == "missing"
        assert slots[3].expected_month == "2025-05"

    def test_no_slots_when_nothing_captured_has_a_position(self):
        assert build_slots(12, [], today=date(2025, 1, 1)) == []

    def test_positions_beyond_total_are_ignored(self):
        assert build_slots(2, [_cap(5, date(2025, 1, 31))], today=date(2025, 1, 31)) == []

    def test_fully_captured_plan_has_no_gaps(self):
        captured = [_cap(1, date(2025, 1, 31)), _cap(2, date(2025, 2, 28))]
        assert {s.status for s in build_slots(2, captured, today=date(2025, 6, 1))} == {"captured"}

from datetime import date

from app.features.travel.checklist.template import ChecklistItem, DEFAULT_ITEMS, due_date, parse_items


class TestParseItems:
    def test_reads_anchor_slug_and_signed_offset(self):
        items = parse_items({"travel.checklist.start.plug-adapter": "-7", "travel.checklist.end.send-photos": "3"})
        assert [(i.anchor, i.slug, i.offset_days) for i in items] == [("start", "plug-adapter", -7), ("end", "send-photos", 3)]

    def test_title_humanizes_the_slug(self):
        assert ChecklistItem("start", "online-check_in", -1).title == "online check in"

    def test_ignores_bad_values_unknown_anchors_and_missing_slugs_without_raising(self, caplog):
        items = parse_items({
            "travel.checklist.start.ok": "0",
            "travel.checklist.start.bad": "soon",
            "travel.checklist.middle.x": "1",
            "travel.checklist.start": "1",
            "travel.checklist_seeded": "1",
        })
        assert [i.slug for i in items] == ["ok"]
        assert "not an integer" in caplog.text

    def test_start_items_come_first_ordered_by_offset(self):
        items = parse_items({
            "travel.checklist.end.b": "1", "travel.checklist.start.late": "-1", "travel.checklist.start.early": "-30",
        })
        assert [i.slug for i in items] == ["early", "late", "b"]

    def test_defaults_are_six_start_and_two_end(self):
        assert [a for a, _, _ in DEFAULT_ITEMS].count("start") == 6
        assert [a for a, _, _ in DEFAULT_ITEMS].count("end") == 2


class TestDueDate:
    def test_start_anchor_counts_back_from_the_start(self):
        item = ChecklistItem("start", "x", -7)
        assert due_date(item, date(2026, 12, 17), date(2026, 12, 29), date(2026, 11, 12)) == date(2026, 12, 10)

    def test_end_anchor_counts_from_the_end_regardless_of_trip_length(self):
        item = ChecklistItem("end", "x", 3)
        assert due_date(item, date(2026, 12, 17), date(2026, 12, 29), date(2026, 11, 12)) == date(2027, 1, 1)

    def test_a_date_already_past_is_moved_to_today(self):
        item = ChecklistItem("start", "x", -60)
        assert due_date(item, date(2026, 12, 17), date(2026, 12, 29), date(2026, 11, 12)) == date(2026, 11, 12)

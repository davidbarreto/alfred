from app.features.language.level_guidance import CEFR_LEVELS, level_guidance


class TestCefrLevels:
    def test_includes_a0_through_c2(self):
        assert CEFR_LEVELS == ("A0", "A1", "A2", "B1", "B2", "C1", "C2")


class TestLevelGuidance:
    def test_a0_mentions_total_beginner(self):
        guidance = level_guidance("A0", "French")
        assert "essentially no French yet" in guidance

    def test_c2_mentions_native_level(self):
        guidance = level_guidance("C2", "French")
        assert "native-level" in guidance

    def test_interpolates_language_name(self):
        assert "Spanish" in level_guidance("A0", "Spanish")

    def test_lowercase_level_is_normalized(self):
        assert level_guidance("a0", "French") == level_guidance("A0", "French")

    def test_unknown_level_falls_back_to_a1(self):
        assert level_guidance("Z9", "French") == level_guidance("A1", "French")

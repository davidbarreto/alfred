from app.features.cs.normalization import (
    normalize_cf_difficulty,
    normalize_language,
    normalize_leetcode_difficulty,
    normalize_tag_name,
    normalize_verdict,
)


class TestNormalizeLanguage:
    def test_maps_known_aliases(self):
        assert normalize_language("GNU C++17") == "cpp"
        assert normalize_language("python3") == "python"
        assert normalize_language("PyPy3") == "python"

    def test_returns_none_for_unknown(self):
        assert normalize_language("brainfuck") is None

    def test_returns_none_for_empty(self):
        assert normalize_language(None) is None
        assert normalize_language("") is None


class TestNormalizeTagName:
    def test_collapses_known_alias(self):
        assert normalize_tag_name("dp") == "dynamic programming"
        assert normalize_tag_name("Dynamic Programming") == "dynamic programming"

    def test_passes_through_unknown_tag_lowercased(self):
        assert normalize_tag_name("Some New Tag") == "some new tag"


class TestNormalizeVerdict:
    def test_maps_codeforces_ok_to_accepted(self):
        assert normalize_verdict("OK") == "accepted"

    def test_maps_leetcode_accepted(self):
        assert normalize_verdict("Accepted") == "accepted"

    def test_maps_wrong_answer_variants(self):
        assert normalize_verdict("WRONG_ANSWER") == "wrong_answer"
        assert normalize_verdict("Wrong Answer") == "wrong_answer"

    def test_unknown_verdict_falls_back_to_other(self):
        assert normalize_verdict("SOMETHING_WEIRD") == "other"


class TestNormalizeCfDifficulty:
    def test_below_1200_is_easy(self):
        assert normalize_cf_difficulty(800) == "easy"
        assert normalize_cf_difficulty(1199) == "easy"

    def test_1200_to_1899_is_medium(self):
        assert normalize_cf_difficulty(1200) == "medium"
        assert normalize_cf_difficulty(1899) == "medium"

    def test_1900_and_above_is_hard(self):
        assert normalize_cf_difficulty(1900) == "hard"
        assert normalize_cf_difficulty(3500) == "hard"

    def test_none_rating_is_none(self):
        assert normalize_cf_difficulty(None) is None


class TestNormalizeLeetcodeDifficulty:
    def test_lowercases(self):
        assert normalize_leetcode_difficulty("Easy") == "easy"
        assert normalize_leetcode_difficulty("Hard") == "hard"

    def test_none_for_empty(self):
        assert normalize_leetcode_difficulty(None) is None

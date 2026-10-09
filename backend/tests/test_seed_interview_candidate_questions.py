import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "db" / "seeds"))

from seed_interview_candidate_questions import _load_questions  # noqa: E402

_CATEGORIES = {"Onboarding", "Tech", "Culture", "Benefits", "Logistics", "Growth", "Work-life"}


class TestLoadQuestions:
    def test_loads_unique_questions(self):
        texts = [text for text, _ in _load_questions()]
        assert len(texts) > 20
        assert len(texts) == len(set(texts))

    def test_every_category_is_a_known_one(self):
        assert {category for _, category in _load_questions()} <= _CATEGORIES

    def test_every_category_is_used(self):
        assert {category for _, category in _load_questions()} == _CATEGORIES

    def test_texts_fit_the_column(self):
        assert all(len(text) <= 500 for text, _ in _load_questions())

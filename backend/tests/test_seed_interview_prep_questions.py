import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "db" / "seeds"))

from seed_interview_prep_questions import _load_questions  # noqa: E402


class TestLoadQuestions:
    def test_loads_non_empty_unique_questions(self):
        questions = _load_questions()
        assert len(questions) > 30
        assert all(q for q in questions)
        assert len(questions) == len(set(questions))

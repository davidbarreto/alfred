import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "db" / "seeds"))

from seed_interview_prep_questions import _load_questions  # noqa: E402


class TestLoadQuestions:
    def test_loads_unique_questions_each_with_tags(self):
        questions = _load_questions()
        texts = [text for text, _ in questions]
        assert len(texts) > 30
        assert len(texts) == len(set(texts))
        assert all(tags for _, tags in questions), "every seeded question should carry at least one tag"

    def test_tags_are_lowercase_kebab_case(self):
        tags = {tag for _, tags in _load_questions() for tag in tags}
        assert all(re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", tag) for tag in tags), sorted(tags)

    def test_no_duplicate_tags_within_a_question(self):
        for text, tags in _load_questions():
            assert len(tags) == len({t.lower() for t in tags}), text

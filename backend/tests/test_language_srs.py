import pytest
from datetime import datetime, timezone, timedelta

from app.features.language.srs import (
    CardState,
    Rating,
    State,
    is_leech,
    next_card_state,
    quality_to_rating,
)

_NOW = datetime(2026, 6, 25, 12, 0, 0, tzinfo=timezone.utc)


def _new_card() -> CardState:
    return CardState(
        stability=0.0,
        difficulty=5.0,
        due_at=_NOW,
        last_review_at=None,
        repetitions=0,
        lapses=0,
        consecutive_failures=0,
        state=State.NEW,
    )


class TestQualityToRating:
    def test_very_low_score_is_again(self):
        assert quality_to_rating(0.0) == Rating.AGAIN
        assert quality_to_rating(1.4) == Rating.AGAIN

    def test_low_score_is_hard(self):
        assert quality_to_rating(1.5) == Rating.HARD
        assert quality_to_rating(2.4) == Rating.HARD

    def test_medium_score_is_good(self):
        assert quality_to_rating(2.5) == Rating.GOOD
        assert quality_to_rating(3.4) == Rating.GOOD

    def test_high_score_is_easy(self):
        assert quality_to_rating(3.5) == Rating.EASY
        assert quality_to_rating(5.0) == Rating.EASY


class TestNewCardReview:
    def test_again_on_new_card_goes_to_learning(self):
        card = next_card_state(_new_card(), Rating.AGAIN, _NOW)
        assert card.state == State.LEARNING
        assert card.consecutive_failures == 1
        assert card.lapses == 0
        assert card.due_at > _NOW

    def test_good_on_new_card_goes_to_learning(self):
        card = next_card_state(_new_card(), Rating.GOOD, _NOW)
        assert card.state == State.LEARNING
        assert card.repetitions == 1
        assert card.consecutive_failures == 0
        assert card.stability > 0

    def test_easy_on_new_card_goes_straight_to_review(self):
        card = next_card_state(_new_card(), Rating.EASY, _NOW)
        assert card.state == State.REVIEW
        assert card.repetitions == 1

    def test_good_stability_is_larger_than_hard(self):
        card_good = next_card_state(_new_card(), Rating.GOOD, _NOW)
        card_hard = next_card_state(_new_card(), Rating.HARD, _NOW)
        assert card_good.stability > card_hard.stability

    def test_easy_stability_is_largest(self):
        card_easy = next_card_state(_new_card(), Rating.EASY, _NOW)
        card_good = next_card_state(_new_card(), Rating.GOOD, _NOW)
        assert card_easy.stability > card_good.stability


class TestReviewCard:
    def _make_review_card(self) -> CardState:
        return CardState(
            stability=10.0,
            difficulty=5.0,
            due_at=_NOW,
            last_review_at=_NOW - timedelta(days=10),
            repetitions=3,
            lapses=0,
            consecutive_failures=0,
            state=State.REVIEW,
        )

    def test_good_recall_increases_stability(self):
        card = self._make_review_card()
        new_card = next_card_state(card, Rating.GOOD, _NOW)
        assert new_card.stability > card.stability

    def test_good_recall_goes_to_review_state(self):
        card = self._make_review_card()
        new_card = next_card_state(card, Rating.GOOD, _NOW)
        assert new_card.state == State.REVIEW

    def test_again_increments_lapses(self):
        card = self._make_review_card()
        new_card = next_card_state(card, Rating.AGAIN, _NOW)
        assert new_card.lapses == card.lapses + 1

    def test_again_goes_to_relearning(self):
        card = self._make_review_card()
        new_card = next_card_state(card, Rating.AGAIN, _NOW)
        assert new_card.state == State.RELEARNING

    def test_again_increments_consecutive_failures(self):
        card = self._make_review_card()
        new_card = next_card_state(card, Rating.AGAIN, _NOW)
        assert new_card.consecutive_failures == 1

    def test_good_resets_consecutive_failures(self):
        card = self._make_review_card()
        card.consecutive_failures = 3
        new_card = next_card_state(card, Rating.GOOD, _NOW)
        assert new_card.consecutive_failures == 0

    def test_due_date_is_in_future(self):
        card = self._make_review_card()
        new_card = next_card_state(card, Rating.GOOD, _NOW)
        assert new_card.due_at > _NOW


class TestLeechDetection:
    def test_not_leech_below_threshold(self):
        assert not is_leech(0)
        assert not is_leech(7)

    def test_leech_at_threshold(self):
        assert is_leech(8)
        assert is_leech(15)


class TestIntervalGrowth:
    def test_intervals_grow_with_successive_good_reviews(self):
        card = _new_card()
        intervals = []
        for _ in range(5):
            card = next_card_state(card, Rating.GOOD, _NOW)
            intervals.append((card.due_at - _NOW).days)

        for i in range(len(intervals) - 1):
            assert intervals[i + 1] >= intervals[i], (
                f"Interval did not grow: {intervals}"
            )

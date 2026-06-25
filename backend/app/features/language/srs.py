"""
FSRS-5 spaced repetition algorithm.

Reference: https://github.com/open-spaced-repetition/fsrs4anki
Stability = number of days for ~90% retention.
Interval ≈ stability (for REQUESTED_RETENTION=0.9).
"""
import math
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import IntEnum

_W = [
    0.4072, 1.1829, 3.1262, 15.4722,
    7.2102, 0.5316, 1.0651, 0.0589,
    1.4675, 0.1134, 0.9813, 1.9395,
    0.1100, 0.2900, 2.2700, 0.1500, 2.9898,
    0.51, 0.29,
]

_DECAY = -0.5
_FACTOR = 0.9 ** (1 / _DECAY) - 1  # ≈ 19/81
_REQUESTED_RETENTION = 0.9
_LEECH_THRESHOLD = 8


class Rating(IntEnum):
    AGAIN = 1
    HARD = 2
    GOOD = 3
    EASY = 4


class State(str):
    NEW = "new"
    LEARNING = "learning"
    REVIEW = "review"
    RELEARNING = "relearning"


@dataclass
class CardState:
    stability: float
    difficulty: float
    due_at: datetime
    last_review_at: datetime | None
    repetitions: int
    lapses: int
    consecutive_failures: int
    state: str


def quality_to_rating(quality_score: float) -> Rating:
    if quality_score < 1.5:
        return Rating.AGAIN
    if quality_score < 2.5:
        return Rating.HARD
    if quality_score < 3.5:
        return Rating.GOOD
    return Rating.EASY


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def _retrievability(elapsed_days: float, stability: float) -> float:
    if stability <= 0:
        return 0.0
    return (1 + _FACTOR * elapsed_days / stability) ** _DECAY


def _next_interval(stability: float) -> int:
    interval = stability / _FACTOR * (_REQUESTED_RETENTION ** (1 / _DECAY) - 1)
    return max(1, round(interval))


def _init_stability(rating: Rating) -> float:
    return _W[rating - 1]


def _init_difficulty(rating: Rating) -> float:
    d = _W[4] - math.exp(_W[5] * (rating - 1)) + 1
    return _clamp(d, 1.0, 10.0)


def _next_difficulty(d: float, rating: Rating) -> float:
    d_new = d - _W[6] * (rating - 3)
    return _clamp(_W[7] * _W[4] + (1 - _W[7]) * d_new, 1.0, 10.0)


def _next_recall_stability(d: float, s: float, r: float, rating: Rating) -> float:
    hard_penalty = _W[15] if rating == Rating.HARD else 1.0
    easy_bonus = _W[16] if rating == Rating.EASY else 1.0
    return s * (
        math.exp(_W[8])
        * (11 - d)
        * s ** (-_W[9])
        * (math.exp((1 - r) * _W[10]) - 1)
        * hard_penalty
        * easy_bonus
        + 1
    )


def _next_forget_stability(d: float, s: float, r: float) -> float:
    return _W[11] * d ** (-_W[12]) * ((s + 1) ** _W[13] - 1) * math.exp((1 - r) * _W[14])


def next_card_state(card: CardState, rating: Rating, now: datetime | None = None) -> CardState:
    """Compute the next FSRS card state after a review with the given rating."""
    now = now or datetime.now(timezone.utc)
    elapsed_days = 0.0
    if card.last_review_at is not None:
        elapsed_days = max(0.0, (now - card.last_review_at).total_seconds() / 86400)

    is_new = card.state == State.NEW

    if is_new:
        stability = _init_stability(rating)
        difficulty = _init_difficulty(rating)
        if rating == Rating.AGAIN:
            new_state = State.LEARNING
            interval_days = 1
        elif rating == Rating.HARD:
            new_state = State.LEARNING
            interval_days = 1
        elif rating == Rating.GOOD:
            new_state = State.LEARNING
            interval_days = max(1, round(stability))
        else:
            new_state = State.REVIEW
            interval_days = _next_interval(stability)
        repetitions = 0 if rating == Rating.AGAIN else 1
        lapses = 0
        consecutive_failures = 1 if rating == Rating.AGAIN else 0
    else:
        r = _retrievability(elapsed_days, card.stability)
        difficulty = _next_difficulty(card.difficulty, rating)

        if rating == Rating.AGAIN:
            stability = _next_forget_stability(card.difficulty, card.stability, r)
            new_state = State.RELEARNING
            interval_days = 1
            repetitions = card.repetitions
            lapses = card.lapses + 1
            consecutive_failures = card.consecutive_failures + 1
        else:
            stability = _next_recall_stability(card.difficulty, card.stability, r, rating)
            new_state = State.REVIEW
            interval_days = _next_interval(stability)
            repetitions = card.repetitions + 1
            lapses = card.lapses
            consecutive_failures = 0

    due_at = now + timedelta(days=interval_days)
    return CardState(
        stability=max(0.1, stability),
        difficulty=difficulty,
        due_at=due_at,
        last_review_at=now,
        repetitions=repetitions,
        lapses=lapses,
        consecutive_failures=consecutive_failures,
        state=new_state,
    )


def is_leech(consecutive_failures: int) -> bool:
    return consecutive_failures >= _LEECH_THRESHOLD

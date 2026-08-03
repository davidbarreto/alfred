from pydantic import BaseModel

from app.features.cs.stats.schemas import CandidateProblem


class LiveRecommendation(BaseModel):
    tag: str | None
    solve_rate: float | None
    reason: str
    candidates: list[CandidateProblem]

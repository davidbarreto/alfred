from pydantic import BaseModel

from app.features.cs.stats.schemas import CandidateProblem


class LiveRecommendation(BaseModel):
    tag: str
    solve_rate: float
    reason: str
    candidates: list[CandidateProblem]

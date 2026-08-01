from pydantic import BaseModel


class CandidateProblem(BaseModel):
    id: int
    platform_id: int
    external_id: str
    name: str
    url: str | None
    difficulty: str | None
    tags: list[str]

    model_config = {"from_attributes": True}


class TagBreakdown(BaseModel):
    tag: str
    attempted: int
    solved: int
    solve_rate: float
    submissions: int
    avg_attempts_per_solve: float | None


class DifficultyBreakdown(BaseModel):
    difficulty: str
    attempted: int
    solved: int


class LanguageBreakdown(BaseModel):
    language: str
    solved: int


class StatsSummary(BaseModel):
    current_streak: int
    longest_streak: int
    total_solved: int
    by_difficulty: list[DifficultyBreakdown]
    by_tag: list[TagBreakdown]
    by_language: list[LanguageBreakdown]
    weakest_tags: list[TagBreakdown]
    untried_tags: list[str]

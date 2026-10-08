from typing import Annotated

from pydantic import BaseModel, StringConstraints


def normalize_tags(tags: list[str] | None) -> list[str] | None:
    """Trim, drop blanks and case-insensitive duplicates (first spelling wins), enforce the length cap."""
    if tags is None:
        return None
    normalized: list[str] = []
    seen: set[str] = set()
    for tag in tags:
        cleaned = tag.strip()
        if not cleaned or cleaned.lower() in seen:
            continue
        if len(cleaned) > 100:
            raise ValueError("tags must be at most 100 characters")
        seen.add(cleaned.lower())
        normalized.append(cleaned)
    return normalized


class InterviewTagRead(BaseModel):
    id: int
    name: str

    model_config = {"from_attributes": True}


class InterviewTagUsage(BaseModel):
    id: int
    name: str
    story_count: int
    question_count: int


class InterviewTagUpdate(BaseModel):
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]

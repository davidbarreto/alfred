from __future__ import annotations

import functools
from typing import Literal

from pydantic import BaseModel, Field
from pydantic_ai import Agent
from pydantic_ai.models.google import GoogleModel
from pydantic_ai.providers.google import GoogleProvider

from app.config import get_settings


class CreateTaskArgs(BaseModel):
    title: str
    due_date: str | None = Field(default=None)
    priority: Literal["low", "medium", "high"] | None = Field(default=None)


class GetTasksArgs(BaseModel):
    filter: str | None = Field(default=None)


class CreateNoteArgs(BaseModel):
    title: str | None = Field(default=None)
    content: str


class GetCalendarArgs(BaseModel):
    date_range: str | None = Field(default=None)


_SYSTEM_PROMPT = (
    "Extract the requested structured fields from the user message. "
    "Return only the extracted field values — no explanation or commentary."
)

_INTENT_SCHEMAS: dict[str, type[BaseModel]] = {
    "task.add": CreateTaskArgs,
    "task.list": GetTasksArgs,
    "note.add": CreateNoteArgs,
    "event.list": GetCalendarArgs,
}


@functools.lru_cache(maxsize=None)
def _get_agent(intent: str) -> Agent | None:
    schema = _INTENT_SCHEMAS.get(intent)
    if schema is None:
        return None
    settings = get_settings()
    model = GoogleModel(
        settings.llm_model,
        provider=GoogleProvider(api_key=settings.google_api_key),
    )
    return Agent(model, output_type=schema, system_prompt=_SYSTEM_PROMPT)


async def extract_args(intent: str, text: str) -> dict:
    agent = _get_agent(intent)
    if agent is None:
        return {}
    result = await agent.run(text)
    return result.output.model_dump()

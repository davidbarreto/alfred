from __future__ import annotations

import json
import logging
import time
from typing import Literal

from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations.llm_calls.repository import create_llm_call
from app.shared.llm import LlmProvider

logger = logging.getLogger(__name__)


class CreateTaskArgs(BaseModel):
    title: str
    due_date: str | None = Field(default=None)
    priority: Literal["low", "medium", "high"] | None = Field(default=None)


class GetTasksArgs(BaseModel):
    filter: str | None = Field(default=None)


class CreateNoteArgs(BaseModel):
    title: str | None = Field(default=None)
    content: str | None = Field(default=None)


class GetCalendarArgs(BaseModel):
    date_range: str | None = Field(default=None)


_INTENT_SCHEMAS: dict[str, type[BaseModel]] = {
    "task.add": CreateTaskArgs,
    "task.list": GetTasksArgs,
    "note.add": CreateNoteArgs,
    "event.list": GetCalendarArgs,
}

_SYSTEM_PROMPT_TEMPLATE = (
    "Extract the requested structured fields from the user message. "
    "Return ONLY a valid JSON object matching this schema — no explanation or commentary:\n{schema}"
)


async def extract_args(
    intent: str,
    text: str,
    llm_provider: LlmProvider,
    session: AsyncSession | None = None,
) -> dict:
    schema_cls = _INTENT_SCHEMAS.get(intent)
    if schema_cls is None:
        return {}

    system_prompt = _SYSTEM_PROMPT_TEMPLATE.format(
        schema=json.dumps(schema_cls.model_json_schema(), indent=2)
    )
    messages = [{"role": "user", "content": text}]

    try:
        t0 = time.monotonic()
        llm_response = await llm_provider.complete(messages, system=system_prompt)
        latency_ms = int((time.monotonic() - t0) * 1000)

        if session is not None:
            await create_llm_call(
                session,
                provider=llm_provider.provider,
                model=llm_provider.model,
                feature=f"intent_extraction.{intent}",
                prompt=[{"role": "system", "content": system_prompt}] + messages,
                response=llm_response.text,
                tokens_input=llm_response.tokens_input,
                tokens_output=llm_response.tokens_output,
                latency_ms=latency_ms,
            )

        parsed = schema_cls.model_validate_json(llm_response.text)
        return parsed.model_dump()
    except Exception as exc:
        logger.warning("LLM extraction failed (intent=%s): %s", intent, exc)
        return {}

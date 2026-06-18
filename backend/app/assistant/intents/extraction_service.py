from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone
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


class CreateEventArgs(BaseModel):
    title: str = Field(description="Name of the event")
    start: str | None = Field(default=None, description="Start datetime in ISO 8601 format (YYYY-MM-DDTHH:MM:SS). Resolve relative expressions like 'next Sunday' using the current date provided.")
    end: str | None = Field(default=None, description="End datetime in ISO 8601 format. Compute from duration hints like '1h' if no explicit end time is given.")
    additional_notes: str | None = Field(default=None)
    recurrence: str | None = Field(default=None, description="Recurrence rule, e.g. 'weekly', 'daily', 'every Monday'")


_INTENT_SCHEMAS: dict[str, type[BaseModel]] = {
    "task.add": CreateTaskArgs,
    "task.list": GetTasksArgs,
    "note.add": CreateNoteArgs,
    "event.add": CreateEventArgs,
    "event.list": GetCalendarArgs,
}

_INTENTS_WITH_DATES = {"task.add", "event.add", "event.list"}

_DATE_CONTEXT = "The current date and time is {now}. Use it to resolve relative date expressions like 'next Sunday' or 'tomorrow'. "

_SYSTEM_PROMPT_TEMPLATE = (
    "Extract the requested structured fields from the user message. "
    "{date_context}"
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

    schema_str = json.dumps(schema_cls.model_json_schema(), indent=2)
    date_context = ""
    if intent in _INTENTS_WITH_DATES:
        now = datetime.now(tz=timezone.utc).strftime("%A, %B %d, %Y at %H:%M UTC")
        date_context = _DATE_CONTEXT.format(now=now)
    system_prompt = _SYSTEM_PROMPT_TEMPLATE.format(date_context=date_context, schema=schema_str)
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

        raw = llm_response.text.strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
        parsed = schema_cls.model_validate_json(raw)
        result = parsed.model_dump()
        logger.debug("Extraction successful: intent=%s fields=%s", intent, list(result.keys()))
        return result
    except Exception as exc:
        logger.warning("LLM extraction failed (intent=%s): %s", intent, exc)
        return {}

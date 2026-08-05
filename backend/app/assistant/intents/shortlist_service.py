from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.assistant.commands.registry import COMMAND_DEFINITIONS
from app.assistant.commands.schemas import CommandDetail
from app.assistant.intents.extraction_service import get_schema_for_intent
from app.assistant.intents.intent_service import IntentResult
from app.assistant.prompts import DATE_CONTEXT_TEMPLATE, INTENT_SHORTLIST_PROMPT_TEMPLATE
from app.integrations.llm_calls.repository import create_llm_call
from app.shared.llm import LlmProvider

logger = logging.getLogger(__name__)


def _intent_description(intent: str) -> str:
    cmd_type, _, action = intent.partition(".")
    return COMMAND_DEFINITIONS.get(cmd_type, {}).get(action, {}).get("description", "")


async def resolve_via_shortlist(
    text: str,
    candidates: list[IntentResult],
    llm_provider: LlmProvider,
    session: AsyncSession | None = None,
) -> CommandDetail | None:
    """Classify + extract in one LLM call, constrained to a pre-filtered shortlist of
    candidate intents (from embedding similarity) rather than the full command catalog —
    keeps the prompt small and the LLM's output space narrow. Used only when no single
    intent clears the embedding confidence threshold on its own."""
    if not candidates:
        return None

    candidates_by_intent = {c.intent: c for c in candidates}
    catalog = [
        {
            "intent": c.intent,
            "description": _intent_description(c.intent),
            "args_schema": (schema_cls.model_json_schema() if (schema_cls := get_schema_for_intent(c.intent)) else None),
        }
        for c in candidates
    ]

    now = datetime.now(tz=timezone.utc).strftime("%A, %B %d, %Y at %H:%M UTC")
    system_prompt = INTENT_SHORTLIST_PROMPT_TEMPLATE.format(
        date_context=DATE_CONTEXT_TEMPLATE.format(now=now),
        catalog=json.dumps(catalog, indent=2),
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
                feature="intent_shortlist",
                prompt=[{"role": "system", "content": system_prompt}] + messages,
                response=llm_response.text,
                tokens_input=llm_response.tokens_input,
                tokens_output=llm_response.tokens_output,
                finish_reason=llm_response.finish_reason,
                latency_ms=latency_ms,
            )

        raw = llm_response.text.strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
        parsed = json.loads(raw)

        intent = parsed.get("intent")
        if not intent or intent not in candidates_by_intent:
            logger.debug("Shortlist: no candidate selected (intent=%r) text=%r", intent, text[:80])
            return None

        args = parsed.get("args") or {}
        schema_cls = get_schema_for_intent(intent)
        if schema_cls is not None:
            args = schema_cls.model_validate(args).model_dump()

        cmd_type, _, cmd_action = intent.partition(".")
        confidence = candidates_by_intent[intent].confidence
        logger.info("Shortlist resolved: intent=%s confidence=%.4f", intent, confidence)
        return CommandDetail(
            type=cmd_type,
            command=cmd_action,
            confidence=confidence,
            source="llm_shortlist",
            args=args,
        )
    except Exception as exc:
        logger.warning("Shortlist resolution failed text=%r error=%s", text[:80], exc)
        return None

import re
import shlex
from datetime import datetime, date
from typing import List, Dict, Any, Tuple

from sqlalchemy.ext.asyncio import AsyncSession

from app.assistant.commands.registry import COMMAND_REGISTRY
from app.assistant.commands.schemas import CommandDetail, CommandResolveResponse
from app.assistant.intents.intent_service import detect_intent
from app.assistant.intents.extraction_service import extract_args
from app.config import get_settings
from app.nlp.normalizer import normalize_date, normalize_priority, clean_text
from app.nlp.extractor import extract_entities, extract_finance_entities


def _normalize_date(date_str: str, base_date: datetime | date | None = None) -> str | None:
    """Convert relative date keywords or strings to ISO format."""
    if not date_str:
        return None
    try:
        if base_date is None:
            effective_base = datetime.now()
        elif isinstance(base_date, datetime):
            effective_base = base_date
        else:
            effective_base = datetime.combine(base_date, datetime.min.time())
        return normalize_date(date_str, base_date=effective_base)
    except Exception as ex:
        print(f"Error normalizing date: {ex}")
        return None


def _parse_tokens(text: str) -> List[str]:
    """Safely split text into tokens, handling quotes."""
    try:
        return shlex.split(text)
    except ValueError:
        return text.split()


def _split_command_fragments(text: str) -> List[str]:
    """Split the message into slash command fragments."""
    fragments = [fragment.strip() for fragment in re.split(r"(?<=\s)(?=/)", text.strip()) if fragment.strip()]
    return fragments


def _extract_args_and_flags(tokens: List[str], flag_definitions: Dict[str, str]) -> Tuple[List[str], Dict[str, Any]]:
    """Separate positional arguments from flags defined in flag_definitions."""
    _canonical_by_name: Dict[str, str] = {}
    for flag_key, canonical in flag_definitions.items():
        _canonical_by_name[flag_key.lstrip('-')] = canonical
        _canonical_by_name[canonical] = canonical

    args = []
    flags = {}
    i = 0
    key = None
    while i < len(tokens):
        token = tokens[i]
        found = False
        if token in flag_definitions:
            found = True
            key = flag_definitions[token]
        else:
            stripped = token.lstrip('-')
            for flag in (f"--{stripped}", f"-{stripped}"):
                if flag in flag_definitions:
                    found = True
                    key = flag_definitions[flag]
                    break

        if not found and ':' in token:
            kv_key, kv_val = token.split(':', 1)
            canonical = _canonical_by_name.get(kv_key.lower())
            if canonical:
                flags[canonical] = kv_val
                i += 1
                continue

        if found:
            if i + 1 < len(tokens):
                flags[key] = tokens[i+1]
                i += 2
            else:
                flags[key] = True
                i += 1
        else:
            args.append(token)
            i += 1
    return args, flags


def _enrich_finance(arguments: Dict[str, Any]) -> Dict[str, Any]:
    """Finance-specific NLP enrichment."""
    today = datetime.now().date()

    for date_field in ("from_date", "to_date", "date"):
        if date_field in arguments and isinstance(arguments[date_field], str):
            arguments[date_field] = _normalize_date(arguments[date_field], base_date=today) or arguments[date_field]

    if "description" in arguments and isinstance(arguments["description"], str):
        _, entities = extract_finance_entities(arguments["description"], base_date=today)
        for key in ("amount", "currency", "merchant", "type", "date"):
            if key not in arguments and entities.get(key):
                arguments[key] = entities[key]

    return arguments


def _enrich_arguments(arguments: Dict[str, Any], cmd_type: str = "") -> Dict[str, Any]:
    """Normalize arguments and extract implicit entities from text fields."""
    if cmd_type == "finance":
        return _enrich_finance(arguments)

    today = datetime.now().date()

    if "deadline" in arguments and isinstance(arguments["deadline"], str):
        arguments["deadline"] = _normalize_date(arguments["deadline"], base_date=today) or arguments["deadline"]

    if "due" in arguments and isinstance(arguments["due"], str) and not arguments.get("deadline"):
        arguments["deadline"] = _normalize_date(arguments["due"], base_date=today) or arguments["due"]

    if "priority" in arguments and isinstance(arguments["priority"], str):
        arguments["priority"] = normalize_priority(arguments["priority"])

    if "_raw_args" in arguments and isinstance(arguments["_raw_args"], list):
        arguments["task"] = " ".join(arguments.pop("_raw_args"))

    for text_key in ["task", "title", "content", "description"]:
        if text_key in arguments and isinstance(arguments[text_key], str):
            text_val = arguments[text_key]
            cleaned_text, entities = extract_entities(text_val, base_date=today)

            if ("deadline" not in arguments or not arguments["deadline"]) and entities.get("deadline"):
                arguments["deadline"] = entities["deadline"]
            if ("priority" not in arguments or not arguments["priority"]) and entities.get("priority"):
                arguments["priority"] = entities["priority"]

            arguments[text_key] = clean_text(cleaned_text)

    return arguments


def _split_intent(intent: str) -> tuple[str, str]:
    """Split 'task.add' → ('task', 'add'). Returns ('unknown', 'unknown') for bare labels."""
    if "." not in intent:
        return "unknown", "unknown"
    cmd_type, cmd_action = intent.split(".", 1)
    return cmd_type, cmd_action


def _resolve_fragment(cmd_alias: str, remaining_tokens: List[str]) -> CommandDetail | None:
    """Resolve a single command alias + its remaining tokens into a CommandDetail."""
    meta = COMMAND_REGISTRY.get(cmd_alias)
    if not meta:
        return None

    # Handle long-form "/task add …" — strip the action sub-word
    if remaining_tokens and remaining_tokens[0].lower() == meta.action and cmd_alias == f"/{meta.type}":
        remaining_tokens = remaining_tokens[1:]

    args, flags = _extract_args_and_flags(remaining_tokens, meta.flags)

    if meta.requires_args and not args:
        return None

    # Explicit flags override implicit ones set by the alias (e.g. /expense sets type=expense
    # but --type income would still win).
    arguments: Dict[str, Any] = {**meta.implicit_flags, **flags}

    if meta.arg_keys:
        for i, key in enumerate(meta.arg_keys):
            if i < len(args):
                if i == len(meta.arg_keys) - 1:
                    arguments[key] = " ".join(args[i:])
                else:
                    arguments[key] = args[i]
    elif args:
        arguments["_raw_args"] = args

    arguments = _enrich_arguments(arguments, cmd_type=meta.type)

    return CommandDetail(
        type=meta.type,
        command=meta.action,
        confidence=1.0,
        source="deterministic",
        arguments=arguments,
    )


async def resolve(
    text: str,
    command: str | None = None,
    args: str | None = None,
    session: AsyncSession | None = None,
) -> CommandResolveResponse:
    """
    Structured command resolver.

    1. Tries deterministic (slash-command) parsing first.
    2. Falls back to intent detection + argument extraction when no slash commands
       are found and a DB session is available.
    """
    if command:
        tokens = _parse_tokens(args or "")
        cmd = _resolve_fragment(command.lower(), tokens)
        if not cmd:
            return CommandResolveResponse(status="not_parsed", commands=[], raw_text=text)
        return CommandResolveResponse(status="ok", commands=[cmd], raw_text=text)

    fragments = _split_command_fragments(text)
    commands = []
    for fragment in fragments:
        tokens = _parse_tokens(fragment)
        if not tokens:
            continue
        cmd = _resolve_fragment(tokens[0].lower(), tokens[1:])
        if cmd:
            commands.append(cmd)

    if commands:
        return CommandResolveResponse(status="ok", commands=commands, raw_text=text)

    if session is None or not text.strip():
        return CommandResolveResponse(status="not_parsed", commands=[], raw_text=text)

    intent_result = await detect_intent(text, session)
    threshold = get_settings().intent_threshold
    cmd_type, cmd_action = _split_intent(intent_result.intent)

    if intent_result.intent != "unknown" and intent_result.confidence >= threshold:
        extracted = await extract_args(intent_result.intent, text)
        detail = CommandDetail(
            type=cmd_type,
            command=cmd_action,
            confidence=intent_result.confidence,
            source="intent_detection",
            arguments=extracted,
        )
    else:
        detail = CommandDetail(
            type=cmd_type,
            command=cmd_action,
            confidence=intent_result.confidence,
            source="unknown",
            arguments={},
        )

    return CommandResolveResponse(status="ok", commands=[detail], raw_text=text)

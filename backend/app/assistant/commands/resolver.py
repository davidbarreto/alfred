import re
import shlex
from datetime import datetime, date
from typing import List, Dict, Any, Tuple

from app.assistant.commands.registry import COMMAND_REGISTRY
from app.assistant.commands.schemas import CommandDetail, CommandResolveResponse
from app.nlp.normalizer import normalize_date, normalize_priority, clean_text
from app.nlp.extractor import extract_entities

def _normalize_date(date_str: str, base_date: datetime | date | None = None) -> str | None:
    """Convert relative date keywords or strings to ISO format."""
    if not date_str:
        return None
    # Delegate to shared NLP normalizer which includes fallbacks.
    try:
        if base_date is None:
            effective_base = datetime.now()
        elif isinstance(base_date, datetime):
            effective_base = base_date
        else:  # it's a date object
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
    # Build a reverse map from canonical name to canonical name (e.g. "priority" -> "priority")
    # and from stripped flag name to canonical name (e.g. "due" -> "deadline")
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
            # try normalized long/short variants (e.g. '-title' -> '--title')
            stripped = token.lstrip('-')
            for flag in (f"--{stripped}", f"-{stripped}"):
                if flag in flag_definitions:
                    found = True
                    key = flag_definitions[flag]
                    break

        if not found and ':' in token:
            # handle key:value inline syntax (e.g. priority:high, due:tomorrow)
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

def _enrich_arguments(arguments: Dict[str, Any]) -> Dict[str, Any]:
    """
    Normalize existing arguments and extract implicit ones from text fields.
    Ported from concepts in commands_old.py.
    """
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

def resolve(text: str) -> CommandResolveResponse:
    """
    Structured command resolver.
    Uses a deterministic parser to handle task-related commands and flags.
    """
    fragments = _split_command_fragments(text)
    commands = []

    for fragment in fragments:
        tokens = _parse_tokens(fragment)
        if not tokens:
            continue

        cmd_alias = tokens[0].lower()
        meta = COMMAND_REGISTRY.get(cmd_alias)
        if not meta:
            continue

        remaining_tokens = tokens[1:]
        if remaining_tokens and remaining_tokens[0].lower() == meta.action and cmd_alias == f"/{meta.type}":
            remaining_tokens = remaining_tokens[1:]
        args, flags = _extract_args_and_flags(remaining_tokens, meta.flags)

        # Validation for required positional arguments (e.g., title or ID)
        if meta.requires_args and not args:
            continue

        # Build arguments dynamically based on metadata definitions
        arguments = {**flags}
        if meta.arg_keys:
            for i, key in enumerate(meta.arg_keys):
                if i < len(args):
                    # If this is the last expected key, join all remaining positional arguments
                    if i == len(meta.arg_keys) - 1:
                        arguments[key] = " ".join(args[i:])
                    else:
                        arguments[key] = args[i]
        elif args:
            # Fallback for unexpected positional arguments
            arguments["_raw_args"] = args

        # Apply NLP enrichment and normalization pass
        arguments = _enrich_arguments(arguments)

        commands.append(
            CommandDetail(
                type=meta.type,
                command=meta.action,
                confidence=0.99,
                resolver="deterministic",
                arguments=arguments
            )
        )

    if not commands:
        return CommandResolveResponse(status="not_parsed", commands=[], raw_text=text)

    return CommandResolveResponse(
        status="ok",
        commands=commands,
        raw_text=text
    )
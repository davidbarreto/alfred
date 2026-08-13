import logging
import re
from typing import Any

from app.assistant.commands.registry import COMMAND_DEFINITIONS, COMMAND_REGISTRY

logger = logging.getLogger(__name__)

_SEARCH_RESULT_LIMIT = 3

_GROUP_LABELS = {
    "task": "Tasks",
    "note": "Notes",
    "event": "Calendar",
    "shopping": "Shopping",
    "wishlist": "Wishlist",
    "language": "Language",
    "recall": "Memory",
    "weather": "Weather",
    "assistant": "Assistant",
    "reminder": "Reminders",
    "finance": "Finance",
    "help": "Help",
}


def _flags_display(flags: dict[str, str]) -> list[dict[str, Any]]:
    """Group flag aliases by destination key for display."""
    grouped: dict[str, list[str]] = {}
    for flag_str, dest_key in flags.items():
        grouped.setdefault(dest_key, []).append(flag_str)
    return [
        {"key": key, "aliases": sorted(aliases, key=len)}
        for key, aliases in grouped.items()
    ]


def _find_config_by_alias(query: str) -> tuple[str, str, dict] | None:
    """Return (cmd_type, action_name, config) for the first alias that matches query."""
    lookup = f"/{query.lstrip('/')}"
    for cmd_type, actions in COMMAND_DEFINITIONS.items():
        for action_name, config in actions.items():
            if lookup.lower() in [a.lower() for a in config.get("aliases", [])]:
                return cmd_type, action_name, config
    return None


def _tokenize(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", text.lower()))


def _search_commands(query: str, limit: int = _SEARCH_RESULT_LIMIT) -> list[tuple[str, str, dict]]:
    """Rank commands by keyword overlap between the query and their description/name/aliases.

    Lets a free-text query like 'voice conversation a0' surface the right command even when
    the user doesn't remember its alias."""
    query_tokens = _tokenize(query)
    if not query_tokens:
        return []

    scored: list[tuple[int, str, str, dict]] = []
    for cmd_type, actions in COMMAND_DEFINITIONS.items():
        for action_name, config in actions.items():
            haystack = " ".join([
                config.get("description", ""),
                " ".join(config.get("aliases", [])),
                cmd_type,
                action_name,
            ])
            score = len(query_tokens & _tokenize(haystack))
            if score:
                scored.append((score, cmd_type, action_name, config))

    scored.sort(key=lambda item: item[0], reverse=True)
    return [(cmd_type, action_name, config) for _, cmd_type, action_name, config in scored[:limit]]


def handle_help(arguments: dict[str, Any]) -> dict[str, Any]:
    query = (arguments.get("query") or "").strip()

    if not query:
        groups: dict[str, list[dict[str, str]]] = {}
        for cmd_type, actions in COMMAND_DEFINITIONS.items():
            label = _GROUP_LABELS.get(cmd_type, cmd_type.capitalize())
            entries = []
            for action_name, config in actions.items():
                if "action" in config:
                    continue
                entries.append({
                    "command": config["aliases"][0],
                    "description": config.get("description", ""),
                })
            if entries:
                groups[label] = entries
        logger.debug("help: returning summary with %d groups", len(groups))
        return {"type": "summary", "groups": groups}

    found = _find_config_by_alias(query)
    if not found:
        # Also try looking up by intent key like "task.add" or "taskadd" directly via registry
        lookup = query if query.startswith("/") else f"/{query}"
        meta = COMMAND_REGISTRY.get(lookup.lower())
        if meta:
            found_config = COMMAND_DEFINITIONS.get(meta.type, {}).get(meta.action)
            if found_config:
                found = (meta.type, meta.action, found_config)

    if not found:
        matches = _search_commands(query)
        if matches:
            logger.debug("help: query=%r matched %d commands via keyword search", query, len(matches))
            return {
                "type": "search_results",
                "query": query,
                "results": [
                    {
                        "command": f"{cmd_type}.{action_name}",
                        "aliases": config.get("aliases", []),
                        "description": config.get("description", ""),
                    }
                    for cmd_type, action_name, config in matches
                ],
            }
        logger.debug("help: query=%r not found", query)
        return {"type": "not_found", "query": query}

    cmd_type, action_name, config = found
    logger.debug("help: returning detail for %s.%s", cmd_type, action_name)
    return {
        "type": "command",
        "command": f"{cmd_type}.{action_name}",
        "description": config.get("description", ""),
        "aliases": config.get("aliases", []),
        "arg_keys": config.get("arg_keys", []),
        "flags": _flags_display(config.get("flags", {})),
    }

from __future__ import annotations

from typing import Any

from mcp import types

TOOL_PREFIX = "alfred_"

# domains: cmd_type -> action_key -> {action, description, requires_args, arg_keys, flags, implicit_flags}
Catalog = dict[str, dict[str, dict[str, Any]]]


def _tool_name(cmd_type: str) -> str:
    return f"{TOOL_PREFIX}{cmd_type}"


def _domain_from_tool_name(tool_name: str) -> str | None:
    if not tool_name.startswith(TOOL_PREFIX):
        return None
    return tool_name[len(TOOL_PREFIX):]


def _domain_description(actions: dict[str, dict[str, Any]]) -> str:
    lines = ["Set `action` to one of:"]
    for action_key, config in actions.items():
        required = config.get("arg_keys", []) if config.get("requires_args") else []
        optional = sorted(
            set(config.get("flags", []))
            | (set(config.get("arg_keys", [])) - set(required))
        )
        bits = [f"- {action_key}: {config.get('description', '')}"]
        if required:
            bits.append(f"(required: {', '.join(required)})")
        if optional:
            bits.append(f"(optional: {', '.join(optional)})")
        lines.append(" ".join(bits))
    return "\n".join(lines)


def build_tools(catalog: Catalog) -> list[types.Tool]:
    """Generate one MCP tool per Alfred command domain (task, finance, ...).

    Every action within a domain shares one tool with an `action` enum param,
    rather than one tool per action — Alfred has ~50 actions across 12
    domains, and a tool-per-action would crowd out a client's other tools.
    Params are unioned across all actions in the domain and left optional;
    the backend already validates required args per-action and returns a
    clear error, so nothing is lost by not encoding that in the schema.
    """
    tools = []
    for cmd_type, actions in catalog.items():
        params: dict[str, dict[str, str]] = {}
        for config in actions.values():
            for key in [*config.get("arg_keys", []), *config.get("flags", [])]:
                if key == "action":
                    raise ValueError(
                        f"Command {cmd_type}.{config.get('action')} uses 'action' as an arg/flag name, "
                        "which collides with the reserved MCP action-selector property"
                    )
                params.setdefault(key, {"type": "string"})
        schema = {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": list(actions.keys())},
                **params,
            },
            "required": ["action"],
        }
        tools.append(
            types.Tool(
                name=_tool_name(cmd_type),
                description=_domain_description(actions),
                inputSchema=schema,
            )
        )
    return tools


def resolve_call(catalog: Catalog, tool_name: str, arguments: dict[str, Any]) -> tuple[str, str, dict[str, Any]]:
    """Resolve an MCP tool call into (cmd_type, backend_action, args) for /commands/execute."""
    cmd_type = _domain_from_tool_name(tool_name)
    actions = catalog.get(cmd_type) if cmd_type else None
    if not actions:
        raise ValueError(f"Unknown tool: {tool_name!r}")

    action_key = arguments.get("action")
    config = actions.get(action_key) if action_key else None
    if config is None:
        raise ValueError(f"Unknown action {action_key!r} for {tool_name}; valid actions: {sorted(actions)}")

    args = {k: v for k, v in arguments.items() if k != "action" and v is not None}
    args.update(config.get("implicit_flags", {}))

    if config.get("requires_args"):
        missing = [k for k in config.get("arg_keys", []) if not args.get(k)]
        if missing:
            raise ValueError(
                f"{tool_name} action={action_key!r} missing required argument(s): {', '.join(missing)}"
            )

    return cmd_type, config["action"], args

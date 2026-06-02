import re
import shlex
from datetime import datetime, timedelta
from typing import List, Dict, Any, Tuple

from app.core.commands import COMMAND_REGISTRY
from app.schemas.command import CommandDetail, CommandResolveResponse
from app.utils import nlp

class CommandService:
    @staticmethod
    def _normalise_date(date_str: str, base_date: datetime | None = None) -> str | None:
        """Convert relative date keywords or strings to ISO format."""
        if not date_str:
            return None
        # Delegate to shared NLP normalizer which includes fallbacks.
        try:
            effective_base = base_date if base_date is not None else datetime.now()
            return nlp.normalize_date(date_str, base_date=effective_base)
        except Exception:
            return None

    @staticmethod
    def _parse_tokens(text: str) -> List[str]:
        """Safely split text into tokens, handling quotes."""
        try:
            return shlex.split(text)
        except ValueError:
            return text.split()

    @staticmethod
    def _split_command_fragments(text: str) -> List[str]:
        """Split the message into slash command fragments."""
        fragments = [fragment.strip() for fragment in re.split(r"(?<=\s)(?=/)", text.strip()) if fragment.strip()]
        return fragments

    @staticmethod
    def _extract_args_and_flags(tokens: List[str], flag_definitions: Dict[str, str]) -> Tuple[List[str], Dict[str, Any]]:
        """Separate positional arguments from flags defined in flag_definitions."""
        args = []
        flags = {}
        i = 0
        while i < len(tokens):
            token = tokens[i]
            found = False
            if token in flag_definitions:
                found = True
                key = flag_definitions[token]
            else:
                # try normalized long/short variants (e.g. '-title' -> '--title')
                stripped = token.lstrip('-')
                for cand in (f"--{stripped}", f"-{stripped}"):
                    if cand in flag_definitions:
                        found = True
                        key = flag_definitions[cand]
                        break

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

    @staticmethod
    def _enrich_arguments(arguments: Dict[str, Any]) -> Dict[str, Any]:
        """
        Normalize existing arguments and extract implicit ones from text fields.
        Ported from concepts in commands_old.py.
        """
        today = datetime.now().date()

        if "deadline" in arguments and isinstance(arguments["deadline"], str):
            arguments["deadline"] = CommandService._normalise_date(arguments["deadline"], base_date=today) or arguments["deadline"]

        if "due" in arguments and isinstance(arguments["due"], str) and not arguments.get("deadline"):
            arguments["deadline"] = CommandService._normalise_date(arguments["due"], base_date=today) or arguments["due"]

        if "priority" in arguments and isinstance(arguments["priority"], str):
            arguments["priority"] = nlp.normalize_priority(arguments["priority"])

        if "_raw_args" in arguments and isinstance(arguments["_raw_args"], list):
            arguments["task"] = " ".join(arguments.pop("_raw_args"))

        for text_key in ["task", "title", "content", "description"]:
            if text_key in arguments and isinstance(arguments[text_key], str):
                text_val = arguments[text_key]
                cleaned_text, entities = nlp.extract_entities(text_val, base_date=today)

                if ("deadline" not in arguments or not arguments["deadline"]) and entities.get("deadline"):
                    arguments["deadline"] = entities["deadline"]
                if ("priority" not in arguments or not arguments["priority"]) and entities.get("priority"):
                    arguments["priority"] = entities["priority"]

                arguments[text_key] = nlp.clean_text(cleaned_text)

        return arguments

    @staticmethod
    def resolve(text: str) -> CommandResolveResponse:
        """
        Structured command resolver.
        Uses a deterministic parser to handle task-related commands and flags.
        """
        fragments = CommandService._split_command_fragments(text)
        commands = []

        for fragment in fragments:
            tokens = CommandService._parse_tokens(fragment)
            if not tokens:
                continue

            cmd_alias = tokens[0].lower()
            meta = COMMAND_REGISTRY.get(cmd_alias)
            if not meta:
                continue

            remaining_tokens = tokens[1:]
            if remaining_tokens and remaining_tokens[0].lower() == meta.action and cmd_alias == f"/{meta.type}":
                remaining_tokens = remaining_tokens[1:]
            args, flags = CommandService._extract_args_and_flags(remaining_tokens, meta.flags)

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
            arguments = CommandService._enrich_arguments(arguments)

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
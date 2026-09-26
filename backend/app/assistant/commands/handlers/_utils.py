from datetime import datetime
from typing import Any

from fastapi import HTTPException, status


def parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def parse_tags(value: str | None) -> list[str]:
    if not value:
        return []
    return [t.strip() for t in value.split(",") if t.strip()]


def require_int(arguments: dict[str, Any], key: str) -> int:
    value = arguments.get(key)
    if value is None or value == "":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"{key} is required")
    try:
        return int(value)
    except (TypeError, ValueError):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"{key} must be an integer, got {value!r}")


def optional_int(arguments: dict[str, Any], key: str, default: int) -> int:
    if arguments.get(key) in (None, ""):
        return default
    return require_int(arguments, key)

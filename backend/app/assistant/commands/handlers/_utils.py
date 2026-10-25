from datetime import datetime
from typing import Any, TypeVar

from fastapi import HTTPException, status
from pydantic import BaseModel, ValidationError

ModelT = TypeVar("ModelT", bound=BaseModel)


def build_model(model_cls: type[ModelT], **fields: Any) -> ModelT:
    """Build a Pydantic model from command arguments; invalid input becomes a 400 with a readable message."""
    try:
        return model_cls(**fields)
    except ValidationError as exc:
        details = "; ".join(
            f"{'.'.join(str(part) for part in error['loc']) or 'value'}: {error['msg']}" for error in exc.errors()
        )
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=details) from exc


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


def parse_int(value: Any, name: str) -> int | None:
    """Optional whole number argument; empty means unset, anything else non-numeric is a 400."""
    if value is None or str(value).strip() == "":
        return None
    try:
        return int(str(value).strip())
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"{name} must be a whole number, got {value!r}")

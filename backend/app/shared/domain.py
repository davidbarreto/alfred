from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class DomainRecord:
    """Base class for all domain entities persisted through a StorageProvider."""

    id: str | None = field(default=None)

    def to_record(self) -> dict:
        """Serialize to the flat dict the StorageProvider expects."""
        raise NotImplementedError

    @classmethod
    def from_record(cls, record: dict) -> DomainRecord:
        """Deserialize from the flat dict the StorageProvider returns."""
        raise NotImplementedError

    @staticmethod
    def _now_iso() -> str:
        return datetime.utcnow().isoformat()
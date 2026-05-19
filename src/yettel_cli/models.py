from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class PhoneNumber:
    number: str


@dataclass(frozen=True)
class UsageRow:
    name: str
    limit: str
    available: str
    valid_until: str

    def to_dict(self) -> dict[str, str]:
        return {
            "name": self.name,
            "limit": self.limit,
            "available": self.available,
            "valid_until": self.valid_until,
        }


@dataclass(frozen=True)
class UsageResult:
    phone: str
    rows: list[UsageRow]
    fetched_at: datetime

    def to_dict(self) -> dict[str, object]:
        return {
            "phone": self.phone,
            "fetched_at": self.fetched_at.isoformat(timespec="seconds"),
            "rows": [row.to_dict() for row in self.rows],
        }

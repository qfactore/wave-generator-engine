from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class LeverAvailability(StrEnum):
    AVAILABLE = "available"
    LOCKED = "locked"
    FUTURE = "future"
    EXPERIMENTAL_UNCERTIFIED = "experimental_uncertified"
    BLOCKED = "blocked"


@dataclass(frozen=True)
class LeverDefinition:
    lever_id: str
    availability: LeverAvailability
    category: str
    locked_in_exact: bool
    data: dict[str, Any]

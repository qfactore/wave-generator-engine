from dataclasses import dataclass
from enum import StrEnum


class GateAction(StrEnum):
    REJECT = "reject"


@dataclass(frozen=True)
class Gate:
    gate_id: str
    description: str
    authority_source: str
    default_action: GateAction
    error_code: str

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class PlanningResult:
    run_request: dict[str, Any]
    authority_snapshot: dict[str, Any]
    source_profile: dict[str, Any]
    delivery_preset: dict[str, Any]
    planning_profile: dict[str, Any]
    session_pack_plan: dict[str, Any]
    session_plan: dict[str, Any]
    macro_state_plan: dict[str, Any]
    packet_plan: dict[str, Any]
    event_plan: dict[str, Any]
    validation_report: dict[str, Any]

from typing import Any

from wave_generator_engine.errors import ValidationFailure

ALLOWED_TRANSITIONS = {
    "reserved": {"draft"},
    "draft": {"active", "invalid"},
    "active": {"archived", "deprecated"},
    "archived": set(),
    "deprecated": set(),
    "preset_locked": set(),
    "invalid": set(),
}


def validate_transition(current: dict[str, Any], target_status: str) -> None:
    if target_status not in ALLOWED_TRANSITIONS.get(current["profile_status"], set()):
        raise ValidationFailure(
            f"Invalid lifecycle transition: {current['profile_status']} -> {target_status}"
        )

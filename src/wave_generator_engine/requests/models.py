from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class RunRequest:
    source_profile_id: str
    delivery_preset_id: str
    selected_session_ids: tuple[int, ...]
    requested_duration_seconds: int
    requested_export_target: str
    data: dict[str, Any]

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class DeliveryPreset:
    preset_id: str
    source_profile_id: str
    nominal_duration_seconds: int
    default_playback_intensity: float
    executable: bool
    data: dict[str, Any]

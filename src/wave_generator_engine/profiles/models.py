from dataclasses import dataclass
from typing import Any

from wave_generator_engine.domain.profile_status import ProfileStatus
from wave_generator_engine.domain.trust_level import TrustLevel


@dataclass(frozen=True)
class SourceProfile:
    profile_id: str
    display_name: str
    profile_version: str
    profile_status: ProfileStatus
    trust_level: TrustLevel
    immutable: bool
    executable: bool
    content_hash: str
    data: dict[str, Any]

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SourceProfile":
        return cls(
            profile_id=data["profile_id"],
            display_name=data["display_name"],
            profile_version=data["profile_version"],
            profile_status=ProfileStatus(data["profile_status"]),
            trust_level=TrustLevel(data["trust_level"]),
            immutable=data["immutable"],
            executable=data["executable"],
            content_hash=data["content_hash"],
            data=data,
        )

from dataclasses import asdict, dataclass
from enum import StrEnum
from typing import Any

from wave_generator_engine.profiles.hashing import content_hash


class MesoPhraseState(StrEnum):
    BACKGROUND = "background"
    PHRASE_ACTIVE = "phrase_active"


@dataclass(frozen=True)
class MesoScheduleRequest:
    duration_samples: int
    sample_rate_hz: int
    root_seed: int
    policy_id: str
    source_scope: str
    target_packet_count: int | None = None
    target_packet_rate_hz: float | None = None

    def resolved_packet_count(self) -> int:
        if (self.target_packet_count is None) == (self.target_packet_rate_hz is None):
            raise ValueError(
                "Exactly one packet-count or packet-rate constraint is required"
            )
        if self.duration_samples <= 0 or self.sample_rate_hz <= 0:
            raise ValueError("Duration and sample rate must be positive")
        if self.target_packet_count is not None:
            count = self.target_packet_count
        else:
            count = round(
                self.target_packet_rate_hz
                * self.duration_samples / self.sample_rate_hz
            )
        if count < 16:
            raise ValueError("Meso scheduling requires at least 16 packets")
        return count


@dataclass(frozen=True)
class MesoPhraseRecord:
    phrase_id: str
    first_packet_index: int
    last_packet_index: int
    packet_count: int
    onset_sample: int
    end_onset_sample: int
    duration_samples: int
    state_entry: str
    state_exit: str


@dataclass(frozen=True)
class MesoScheduleResult:
    schema_version: str
    request: dict[str, Any]
    onset_samples: tuple[int, ...]
    inter_packet_intervals: tuple[int, ...]
    phrase_states: tuple[str, ...]
    packet_phrase_ids: tuple[str | None, ...]
    phrases: tuple[MesoPhraseRecord, ...]
    metrics: dict[str, Any]
    provenance: dict[str, Any]
    content_hash: str

    def to_dict(self) -> dict[str, Any]:
        value = {
            "schema_version": self.schema_version,
            "request": self.request,
            "onset_samples": list(self.onset_samples),
            "inter_packet_intervals": list(self.inter_packet_intervals),
            "phrase_states": list(self.phrase_states),
            "packet_phrase_ids": list(self.packet_phrase_ids),
            "phrases": [asdict(item) for item in self.phrases],
            "metrics": self.metrics,
            "provenance": self.provenance,
            "content_hash": self.content_hash,
        }
        return value

    @staticmethod
    def hash_document(document: dict[str, Any]) -> str:
        return content_hash(document)

import json
from pathlib import Path
from typing import Any

from wave_generator_engine.errors import ValidationFailure
from wave_generator_engine.profiles.hashing import content_hash
from .pipeline import PlanningPipeline


def load_request(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValidationFailure("Run request is unreadable") from exc
    if not isinstance(value, dict):
        raise ValidationFailure("Run request must be an object")
    return value


class PlanningService:
    def __init__(self, interchange_dir: Path | None = None) -> None:
        self.pipeline = PlanningPipeline(interchange_dir)

    def build(self, request: dict[str, Any]):
        return self.pipeline.build(request)

    def build_file(self, path: Path):
        return self.build(load_request(path))

    @staticmethod
    def core_hashes(result) -> dict[str, str]:
        return {
            "request": content_hash(result.run_request),
            "planning_profile": result.planning_profile["content_hash"],
            "session_pack_plan": result.session_pack_plan["content_hash"],
            "session_plan": result.session_plan["content_hash"],
            "macro_state_plan": result.macro_state_plan["content_hash"],
            "packet_plan": result.packet_plan["content_hash"],
            "event_plan": result.event_plan["content_hash"],
            "validation_report": result.validation_report["content_hash"],
        }

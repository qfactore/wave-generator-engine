from dataclasses import dataclass
from pathlib import Path
from typing import Any

from wave_generator_engine.config import CORE_HANDOFF_PATHS
from wave_generator_engine.errors import ValidationFailure
from .loader import load_json

REQUIRED_ARRAYS = (
    "required_authority_files",
    "required_bank_files",
    "required_schema_files",
    "required_fixture_directories",
    "required_validator_files",
    "required_test_files",
    "required_reports",
)


@dataclass(frozen=True)
class Handoff:
    data: dict[str, Any]
    required_paths: tuple[str, ...]
    schema_paths: tuple[str, ...]
    warnings: tuple[str, ...]


def load_handoff(root: Path) -> Handoff:
    data = load_json(root / "handoff/handoff_manifest.json")
    if not isinstance(data, dict):
        raise ValidationFailure("Handoff manifest must be an object")
    declared: list[str] = []
    for key in REQUIRED_ARRAYS:
        values = data.get(key)
        if not isinstance(values, list) or not all(isinstance(v, str) for v in values):
            raise ValidationFailure(f"Handoff manifest has invalid {key}")
        declared.extend(values)
    required = tuple(dict.fromkeys((*CORE_HANDOFF_PATHS, *declared)))
    missing = [item for item in required if not (root / item).exists()]
    if missing:
        raise ValidationFailure("Unresolved required path: " + ", ".join(missing))
    warnings: list[str] = []
    if data.get("created_by_phase") == "WG-I8" and data.get("completed_phases", [])[-1:] == ["WG-I7"]:
        warnings.append("Completed-phase narrative summary is stale; required arrays govern.")
    checklist = (root / "handoff/ENGINE_CONFORMANCE_CHECKLIST.md").read_text(
        encoding="utf-8"
    ).casefold()
    if "all seven schemas" in checklist and len(data["required_schema_files"]) != 7:
        warnings.append("Checklist schema-count narrative is stale; discovered schemas govern.")
    canonical = load_json(root / "manifests/canonical_interchange_manifest.json")
    fixture_status = canonical.get("sections", {}).get("fixtures", {}).get("status", "")
    if canonical.get("generated_by_phase") == "WG-I8" and fixture_status.startswith("wg_i6_"):
        warnings.append("Canonical fixture narrative predates WG-I8; fixture catalog governs.")
    return Handoff(
        data=data,
        required_paths=required,
        schema_paths=tuple(data["required_schema_files"]),
        warnings=tuple(warnings),
    )

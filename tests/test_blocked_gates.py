import json

import pytest

from wave_generator_engine.config import AUTHORITY_ARTIFACT_SCHEMAS
from wave_generator_engine.errors import GateClosedError
from wave_generator_engine.gates.registry import GateRegistry


def registry(root) -> GateRegistry:
    handoff = json.loads((root / "handoff/handoff_manifest.json").read_text())
    decisions = json.loads((root / "manifests/decision_registry.json").read_text())
    artifacts = [json.loads((root / path).read_text()) for path in AUTHORITY_ARTIFACT_SCHEMAS]
    return GateRegistry.from_authority(handoff, decisions, artifacts)


def test_every_machine_readable_block_has_coverage(interchange_root) -> None:
    gates = registry(interchange_root)
    handoff = json.loads((interchange_root / "handoff/handoff_manifest.json").read_text())
    decisions = json.loads((interchange_root / "manifests/decision_registry.json").read_text())
    ids = set(handoff["blocked_behaviors"])
    for decision in decisions["decisions"]:
        ids.update(decision.get("blocked_alternatives", []))
    for gate_id in ids:
        assert gates.covers(gate_id)


@pytest.mark.parametrize("request_id", [
    "production_wav_generation",
    "diagnostic_wav_generation",
    "production_upload_json_generation",
    "exact_replay_through_transform_logic",
    "macro_unit_only_or_required_generation",
    "fixed_physical_focus_channel",
    "missing_provenance_request",
])
def test_unsafe_requests_are_rejected(interchange_root, request_id) -> None:
    with pytest.raises(GateClosedError):
        registry(interchange_root).reject(request_id)


def test_unknown_request_fails_closed(interchange_root) -> None:
    with pytest.raises(GateClosedError, match="UNKNOWN"):
        registry(interchange_root).reject("new_unsafe_idea")

import json
from pathlib import Path

import pytest

from wave_generator_engine.errors import ValidationFailure
from wave_generator_engine.interchange.loader import parse_required_json
from wave_generator_engine.interchange.manifest import load_handoff


def test_manifest_derives_all_required_paths(interchange_root: Path) -> None:
    handoff = load_handoff(interchange_root)
    assert len(handoff.required_paths) > 40
    assert len(handoff.schema_paths) == 12


def test_narrative_drift_warns_without_failure(interchange_root: Path) -> None:
    warnings = load_handoff(interchange_root).warnings
    assert len(warnings) >= 2
    assert any("schema-count" in item for item in warnings)


def test_unresolved_required_path_fails(authority_copy: Path) -> None:
    manifest_path = authority_copy / "handoff/handoff_manifest.json"
    data = json.loads(manifest_path.read_text())
    data["required_reports"].append("reports/missing.json")
    manifest_path.write_text(json.dumps(data))
    with pytest.raises(ValidationFailure, match="Unresolved required path"):
        load_handoff(authority_copy)


def test_malformed_required_json_fails(authority_copy: Path) -> None:
    target = authority_copy / "bank/fixtures/fixture_catalog.json"
    target.write_text("{")
    handoff = load_handoff(authority_copy)
    with pytest.raises(ValidationFailure, match="unreadable"):
        parse_required_json(authority_copy, handoff.required_paths)

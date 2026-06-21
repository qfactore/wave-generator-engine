import json

import pytest

from wave_generator_engine.config import AUTHORITY_ARTIFACT_SCHEMAS
from wave_generator_engine.errors import ValidationFailure
from wave_generator_engine.interchange.loader import parse_required_json
from wave_generator_engine.interchange.manifest import load_handoff
from wave_generator_engine.interchange.schema_validation import (
    compile_schemas, validate_authority_artifacts,
)


def test_every_required_schema_compiles(interchange_root) -> None:
    handoff = load_handoff(interchange_root)
    assert len(compile_schemas(interchange_root, handoff.schema_paths)) == 12


def test_all_five_authority_artifacts_validate(interchange_root) -> None:
    handoff = load_handoff(interchange_root)
    parsed = parse_required_json(interchange_root, handoff.required_paths)
    compiled = compile_schemas(interchange_root, handoff.schema_paths)
    assert len(validate_authority_artifacts(interchange_root, compiled, parsed)) == 5


def test_malformed_artifact_fails(authority_copy) -> None:
    artifact = next(iter(AUTHORITY_ARTIFACT_SCHEMAS))
    path = authority_copy / artifact
    data = json.loads(path.read_text())
    del data["authority_tier"]
    path.write_text(json.dumps(data))
    handoff = load_handoff(authority_copy)
    parsed = parse_required_json(authority_copy, handoff.required_paths)
    compiled = compile_schemas(authority_copy, handoff.schema_paths)
    with pytest.raises(ValidationFailure):
        validate_authority_artifacts(authority_copy, compiled, parsed)


def test_non_2020_schema_fails(authority_copy) -> None:
    handoff = load_handoff(authority_copy)
    path = authority_copy / handoff.schema_paths[0]
    data = json.loads(path.read_text())
    data["$schema"] = "http://json-schema.org/draft-07/schema#"
    path.write_text(json.dumps(data))
    with pytest.raises(ValidationFailure, match="Draft 2020-12"):
        compile_schemas(authority_copy, handoff.schema_paths)

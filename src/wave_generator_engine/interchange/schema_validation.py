from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError, ValidationError

from wave_generator_engine.config import AUTHORITY_ARTIFACT_SCHEMAS
from wave_generator_engine.errors import ValidationFailure
from .loader import load_json

DRAFT_2020_12 = "https://json-schema.org/draft/2020-12/schema"


def compile_schemas(root: Path, schema_paths: tuple[str, ...]) -> dict[str, Draft202012Validator]:
    compiled: dict[str, Draft202012Validator] = {}
    for relative in schema_paths:
        schema = load_json(root / relative)
        dialect = schema.get("$schema") if isinstance(schema, dict) else None
        if dialect not in (DRAFT_2020_12, DRAFT_2020_12 + "#"):
            raise ValidationFailure(f"Schema is not Draft 2020-12 compatible: {relative}")
        try:
            Draft202012Validator.check_schema(schema)
        except SchemaError as exc:
            raise ValidationFailure(f"Invalid schema: {relative}") from exc
        compiled[relative] = Draft202012Validator(schema)
    return compiled


def validate_authority_artifacts(
    root: Path,
    compiled: dict[str, Draft202012Validator],
    parsed: dict[str, Any],
) -> tuple[str, ...]:
    validated: list[str] = []
    for artifact_path, schema_path in AUTHORITY_ARTIFACT_SCHEMAS.items():
        if schema_path not in compiled:
            raise ValidationFailure(f"Required authority schema was not discovered: {schema_path}")
        artifact = parsed.get(artifact_path)
        if artifact is None:
            artifact = load_json(root / artifact_path)
        try:
            compiled[schema_path].validate(artifact)
        except ValidationError as exc:
            raise ValidationFailure(f"Authority artifact failed schema validation: {artifact_path}") from exc
        validated.append(artifact_path)
    return tuple(validated)

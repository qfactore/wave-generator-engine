import copy
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from wave_generator_engine.config import ENGINE_ROOT
from wave_generator_engine.errors import ValidationFailure
from wave_generator_engine.profiles.hashing import validate_content_hash

POLICY_PATH = ENGINE_ROOT / "policies/meso_cluster_rhythm_policy_v1.json"
SCHEMA_PATH = ENGINE_ROOT / "schemas/meso_cluster_rhythm_policy.schema.json"
SUPPORTED_SOURCE_SCOPE = "direct_session_1"


@dataclass(frozen=True)
class MesoPolicy:
    document: dict[str, Any]
    source_scope: str
    parameters: dict[str, Any]

    @property
    def policy_id(self) -> str:
        return self.document["policy_id"]

    @property
    def content_hash(self) -> str:
        return self.document["content_hash"]


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValidationFailure(f"Unable to load meso policy: {path.name}") from exc
    if not isinstance(value, dict):
        raise ValidationFailure("Meso policy must be a JSON object")
    return value


def load_meso_policy(
    source_scope: str,
    policy_path: Path = POLICY_PATH,
    schema_path: Path = SCHEMA_PATH,
) -> MesoPolicy:
    if source_scope != SUPPORTED_SOURCE_SCOPE:
        raise ValidationFailure("Unsupported meso source scope")
    policy = _load_json(policy_path)
    schema = _load_json(schema_path)
    try:
        Draft202012Validator.check_schema(schema)
        Draft202012Validator(schema).validate(policy)
    except Exception as exc:
        raise ValidationFailure("Meso policy schema validation failed") from exc
    if not validate_content_hash(policy):
        raise ValidationFailure("Meso policy content hash mismatch")
    if (
        policy.get("status") != "advisory_non_executable_qualified"
        or policy.get("executable") is not False
        or policy.get("wge5b_meso_cluster_implementation_authorized") is not True
        or policy.get("authorization_blockers")
    ):
        raise ValidationFailure("Meso policy is not qualified for scheduler use")
    if policy["cluster_detection"].get("threshold_samples") is not None:
        raise ValidationFailure("A fixed meso gap threshold is prohibited")
    if policy["cluster_detection"].get("model_type") != \
            "probabilistic_recurrent_interval_phrase_state":
        raise ValidationFailure("Unsupported meso phrase-state model")

    parameters = {
        item["parameter_id"]: copy.deepcopy(item)
        for item in policy["source_supported_parameters"]
    }
    required = {
        "session_1_phrase_active_share",
        "session_1_phrase_initiation_probability",
        "session_1_phrase_continuation_probability",
        "session_1_clusters_per_observed_minute",
        "session_1_cluster_size",
        "session_1_cluster_duration",
        "session_1_within_cluster_interval",
        "session_1_between_cluster_gap",
        "session_1_validation_block_phrase_active_band",
        "session_1_validation_block_cluster_rate_band",
    }
    if not required <= parameters.keys():
        raise ValidationFailure("Required executable meso policy field is unresolved")
    if any(parameters[key].get("value") is None for key in required):
        raise ValidationFailure("Required executable meso policy field is unresolved")
    return MesoPolicy(copy.deepcopy(policy), source_scope, parameters)

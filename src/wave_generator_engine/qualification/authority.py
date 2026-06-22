import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from wave_generator_engine.config import ENGINE_ROOT
from wave_generator_engine.errors import ValidationFailure
from wave_generator_engine.interchange.discovery import discover_interchange
from wave_generator_engine.profiles.hashing import content_hash


@dataclass(frozen=True)
class SourceReference:
    artifact_id: str
    authority_tier: str
    classification_status: str
    path: Path
    source_field: str
    scope: str


def _json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValidationFailure("Source reference must be a JSON object")
    return value


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def select_permitted_artifact(
    artifacts: list[dict[str, Any]], artifact_id: str
) -> dict[str, Any]:
    matches = [item for item in artifacts if item.get("id") == artifact_id]
    if len(matches) != 1:
        raise ValidationFailure("Ambiguous or missing source-reference artifact")
    artifact = matches[0]
    if artifact.get("classification_status") not in {"include", "reference"}:
        raise ValidationFailure("Blocked, archived, or superseded source is not permitted")
    if artifact.get("authority_tier") in {"tier_3", "tier_4", "unknown"}:
        raise ValidationFailure("Tier 3, Tier 4, or unknown material cannot qualify a plan")
    blocked = " ".join(artifact.get("blocked_use", [])).lower()
    if "final-test" in blocked or "final test" in blocked:
        raise ValidationFailure("Final-test material cannot be used for qualification")
    return artifact


class QualificationAuthority:
    def __init__(self, interchange_dir: Path | None = None) -> None:
        self.root = discover_interchange(ENGINE_ROOT, interchange_dir)
        self.source_manifest = _json(self.root / "manifests/source_artifact_manifest.json")
        self.canonical_manifest = _json(
            self.root / "manifests/canonical_interchange_manifest.json"
        )

    def direct(self, artifact_id: str, source_field: str, scope: str) -> SourceReference:
        artifact = select_permitted_artifact(
            self.source_manifest["artifacts"], artifact_id
        )
        path = (self.root / artifact["path"]).resolve()
        expected = artifact["hash"]["value"].removeprefix("sha256:")
        if not path.is_file() or _sha256(path) != expected:
            raise ValidationFailure("Source-reference hash mismatch")
        return SourceReference(
            artifact_id, artifact["authority_tier"],
            artifact["classification_status"], path, source_field, scope,
        )

    def nested_generator_reference(
        self, purpose: str, source_field: str, scope: str
    ) -> SourceReference:
        parent = self.direct(
            "phase5e_generator_model_pack_manifest", "artifacts", scope
        )
        manifest = _json(parent.path)
        matches = [
            item for item in manifest["artifacts"]
            if item.get("purpose") == purpose
            and item.get("classification") in {"generator-facing", "analysis-only"}
        ]
        if len(matches) != 1:
            raise ValidationFailure("Ambiguous nested generator reference")
        record = matches[0]
        path = (self.root.parent / "persinger-analysis" / record["relative_path"]).resolve()
        if not path.is_file() or _sha256(path) != record["sha256"].removeprefix("sha256:"):
            raise ValidationFailure("Nested generator-reference hash mismatch")
        return SourceReference(
            f"phase5e:{purpose.replace(' ', '_')}", "tier_1", "include",
            path, source_field, scope,
        )

    def closure_reference(
        self, relative_path: str, source_field: str, scope: str,
        authority_tier: str = "tier_2",
    ) -> SourceReference:
        closure = self.canonical_manifest["x_alpha_pre_engine_closure"]
        evidence_root = (self.root / closure["evidence_path"]).resolve()
        manifest_path = (self.root / closure["evidence_manifest"]).resolve()
        manifest = _json(manifest_path)
        matches = [item for item in manifest["files"] if item["relative_path"] == relative_path]
        if len(matches) != 1:
            raise ValidationFailure("Closure evidence is missing or ambiguous")
        path = evidence_root / relative_path
        if not path.is_file() or _sha256(path) != matches[0]["sha256"]:
            raise ValidationFailure("Closure evidence hash mismatch")
        if authority_tier not in {"tier_1", "tier_2"}:
            raise ValidationFailure("Low-authority closure evidence cannot qualify a plan")
        return SourceReference(
            f"x_alpha_closure:{relative_path}", authority_tier, "include",
            path, source_field, scope,
        )

    def frozen_session_profile(self, session_id: int) -> SourceReference:
        manifest_ref = self.nested_generator_reference(
            "scheduling freeze manifest", "profile_hashes", f"source_session_{session_id}"
        )
        manifest = _json(manifest_ref.path)
        expected = manifest["profile_hashes"].get(str(session_id), "").removeprefix("sha256:")
        path = manifest_ref.path.parent / f"session_{session_id}_profile.json"
        if not expected or not path.is_file() or content_hash(_json(path)) != expected:
            raise ValidationFailure("Frozen session profile hash mismatch")
        return SourceReference(
            f"phase4d_f:session_{session_id}_profile", "tier_1", "include",
            path, "timing|packet|spatial", f"source_session_{session_id}",
        )

    def inventory(self) -> list[SourceReference]:
        return [
            self.nested_generator_reference(
                "shared scheduling model", "timing_contract", "shared_scheduler_contract"
            ),
            self.nested_generator_reference(
                "scheduling freeze manifest", "profile_hashes", "session_profiles"
            ),
            self.frozen_session_profile(1),
            self.direct(
                "phase5l_mode_specific_unit_grammar_profiles",
                "profiles.baseline_stochastic_texture", "baseline_sessions_1_4",
            ),
            self.direct(
                "phase5l_non_repetition_novelty_audit",
                "modes.baseline_stochastic_texture", "baseline_sessions_1_4",
            ),
            self.direct(
                "phase5e_channel_role_focus_contract", "guidance", "role_normalized"
            ),
            self.closure_reference(
                "data/pulse_pattern_analysis.json", "by_session.1|by_mode.Baseline Mode",
                "session_1_and_baseline_aggregate",
            ),
            self.closure_reference(
                "data/carrier_frequency_analysis.json",
                "source_low_frequency_schedule_spectrum", "source_schedule_spectrum",
            ),
            self.closure_reference(
                "data/macro_density_analysis.json", "recommendation.standard_modes",
                "mode_architecture",
            ),
            self.closure_reference(
                "methods/measurement_methods.md", "measurement_methods",
                "reproducibility_method", "tier_1",
            ),
        ]

import hashlib
import json
from pathlib import Path
from typing import Any

from wave_generator_engine.config import ENGINE_ROOT
from wave_generator_engine.errors import ValidationFailure
from wave_generator_engine.interchange.discovery import discover_interchange
from wave_generator_engine.profiles.hashing import content_hash
from wave_generator_engine.profiles.registry import Registry


def _json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValidationFailure(f"Planning authority is not an object: {path.name}")
    return value


def _file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class PlanningProfileResolver:
    def __init__(self, interchange_dir: Path | None = None) -> None:
        self.root = discover_interchange(ENGINE_ROOT, interchange_dir)
        self.registry = Registry.load()

    def resolve(
        self, source_profile_id: str, delivery_preset_id: str, session_id: int
    ) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
        profile = self.registry.load_entry(source_profile_id)
        preset = self.registry.load_entry(delivery_preset_id)
        if preset["source_profile_id"] != profile["profile_id"]:
            raise ValidationFailure("Delivery preset does not match source profile")
        matches = [
            item for item in profile["session_topology"]["sessions"]
            if item["session_id"] == session_id
        ]
        if len(matches) != 1:
            raise ValidationFailure("Selected session is not in source profile")
        mode = matches[0]["mode_id"]
        mode_status = {
            "baseline": "supported",
            "dense": "mode_not_implemented_in_wge3",
            "complex": "mode_not_implemented_in_wge3",
        }
        if mode_status.get(mode) != "supported":
            raise ValidationFailure("mode_not_implemented_in_wge3")
        authority_paths = {
            "mode_profiles": "bank/mode_profiles/session_mode_profiles.json",
            "unit_terms": "bank/unit_grammar/unit_grammar_terms.json",
            "unit_guidance": "bank/unit_grammar/unit_grammar_guidance.json",
            "hum_putput": "bank/hum_putput/hum_putput_grammar.json",
            "fixture_catalog": "bank/fixtures/fixture_catalog.json",
            "calibration": "bank/calibration/x_alpha_reference_calibration_v1.json",
            "carrier": "bank/grammar/carrier_frequency_policy_v1.json",
            "pulse_pattern": "bank/grammar/pulse_pattern_grammar_v1.json",
            "macro_density": "bank/grammar/macro_density_state_model_v1.json",
            "timing_dependencies": "bank/grammar/timing_dependency_policy_v1.json",
            "decision_registry": "manifests/decision_registry.json",
        }
        documents = {key: _json(self.root / path) for key, path in authority_paths.items()}
        terms = [item["id"] for item in documents["unit_terms"]["terms"]]
        required_terms = {
            "clean_plus_one_sweep", "sweep_with_repeats", "partial_sweep",
            "scattered_packet", "one_impulse_burst", "two_impulse_burst",
            "three_impulse_burst", "packet_start", "packet_continuation",
            "novelty_non_repetition",
        }
        if not required_terms.issubset(terms):
            raise ValidationFailure("Canonical unit grammar is incomplete")
        pulse = documents["pulse_pattern"]["tier_2_mode_profiles"]["Baseline Mode"]
        numeric_guidance = {
            key: {
                "value": value,
                "unit": "count" if "count" in key else (
                    "seconds" if key.endswith("_seconds") else "fraction"
                ),
                "authority_tier": "tier_2",
                "source_artifact": "x_alpha_pulse_pattern_grammar_v1",
                "source_field": f"tier_2_mode_profiles.Baseline Mode.{key}",
                "binding_status": "diagnostic_guidance",
            }
            for key, value in pulse.items()
        }
        provisional_defaults = {
            "packet_interval_distribution": {
                "value": {"distribution": "uniform", "minimum": 0.35, "maximum": 0.65},
                "unit": "seconds",
                "authority_tier": "provisional_diagnostic",
                "source_artifact": "canonical_session_mode_profiles",
                "source_field": "binding_categories.baseline_stochastic_texture",
                "provisional": True,
                "reason": "conservative stochastic diagnostic cadence; no certified packet-interval distribution exists",
                "refinement_required": "compare against authoritative source timing before rendering",
            },
            "continuation_spacing_distributions": {
                "value": {
                    "sweep": {"distribution": "uniform", "minimum": 0.012, "maximum": 0.022},
                    "scattered": {"distribution": "uniform", "minimum": 0.018, "maximum": 0.040},
                    "burst": {"distribution": "uniform", "minimum": 0.008, "maximum": 0.016},
                },
                "unit": "seconds",
                "authority_tier": "provisional_diagnostic",
                "source_artifact": "x_alpha_pulse_pattern_grammar_v1",
                "source_field": "tier_2_mode_profiles.Baseline Mode.cycle_span_median_seconds",
                "provisional": True,
                "reason": "grammar-aware ranges centred below the advisory cycle-span median; certified spacing ranges are absent",
                "refinement_required": "compare by grammar against authoritative source timing before rendering",
            },
            "grammar_weights": {
                "value": {
                    "clean_plus_one_sweep": 0.38,
                    "sweep_with_repeats": 0.17,
                    "partial_sweep": 0.17,
                    "scattered_packet": 0.14,
                    "two_impulse_burst": 0.08,
                    "three_impulse_burst": 0.06,
                },
                "unit": "relative_weight",
                "authority_tier": "provisional_diagnostic",
                "source_artifact": "canonical_unit_grammar_builder_guidance",
                "source_field": "guidance.clean_sweeps",
                "provisional": True,
                "reason": "conditional multi-event grammar coverage; not source-certified probabilities",
            },
            "relative_event_gain": {
                "value": 1.0, "unit": "identity",
                "reason": "neutral metadata value; no gain distribution is certified",
            },
            "novelty_window": {
                "value": 1, "unit": "immediate_previous_event",
                "reason": "minimum safeguard against immediate accidental repetition",
            },
        }
        authority_snapshot = {
            "interchange_manifest_version": _json(
                self.root / "manifests/canonical_interchange_manifest.json"
            )["manifest_version"],
            "files": {
                key: {"artifact_id": documents[key].get("artifact_id", documents[key].get("id")),
                      "sha256": _file_hash(self.root / authority_paths[key])}
                for key in authority_paths
            },
            "tier_3_inputs_used": [],
            "tier_4_inputs_used": [],
        }
        snapshot = {
            "schema_version": "wge.planning_profile_snapshot.v1",
            "snapshot_id": "baseline_diagnostic_planning_v1",
            "mode": "baseline",
            "authority_snapshot": authority_snapshot,
            "grammar_categories": sorted(required_terms),
            "packet_policy": "stochastic_seeded_packets",
            "pulse_pattern_policy": documents["pulse_pattern"]["definition"],
            "channel_grammar_policy": "canonical_unit_grammar_vocabulary",
            "motif_selection_policy": "uniform_exact_frozen_identity_with_immediate_novelty",
            "novelty_repetition_policy": "prevent_immediate_exact_motif_repetition",
            "focus_role_policy": "run_specific_role_bundle",
            "relative_gain_policy": "identity_1_0_provisional_diagnostic",
            "timing_policy": "deterministic_sample_aligned_stochastic_diagnostic",
            "macro_stage_policy": "neutral_active_state_for_baseline",
            "numeric_guidance_used": numeric_guidance,
            "provisional_defaults": provisional_defaults,
            "unsupported_fields": ["carrier_frequency_hz", "motif_time_scale_ratio"],
            "content_hash": "",
        }
        snapshot["content_hash"] = content_hash(snapshot)
        return profile, preset, snapshot, authority_snapshot

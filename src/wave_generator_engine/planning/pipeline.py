import json
from pathlib import Path
from typing import Any

from wave_generator_engine.errors import ValidationFailure
from wave_generator_engine.planning.hashing import content_hash
from wave_generator_engine.planning.models import PlanningResult
from wave_generator_engine.planning.modes import BaselinePlanner, ComplexPlanner, DensePlanner
from wave_generator_engine.planning.profile_resolver import PlanningProfileResolver
from wave_generator_engine.requests.validation import validate_run_request

MODE_PLANNERS = {
    "baseline": BaselinePlanner,
    "dense": DensePlanner,
    "complex": ComplexPlanner,
}


def _identity_metadata(root: Path) -> list[dict[str, Any]]:
    data = json.loads(
        (root / "bank/frozen_assets/frozen_motif_identity_index.json").read_text()
    )
    motifs = data.get("motifs")
    if not isinstance(motifs, list) or len(motifs) != 84:
        raise ValidationFailure("Frozen motif identity metadata is invalid")
    return motifs


class PlanningPipeline:
    stages = (
        "run_request",
        "source_profile_resolution",
        "delivery_preset_resolution",
        "planning_profile_resolution",
        "session_pack_plan",
        "macro_state_stage",
        "packet_grammar_stage",
        "pulse_pattern_stage",
        "channel_grammar_stage",
        "motif_selection_stage",
        "event_plan",
        "plan_validation",
        "diagnostics",
    )

    def __init__(self, interchange_dir: Path | None = None) -> None:
        self.resolver = PlanningProfileResolver(interchange_dir)

    def build(self, request: dict[str, Any]) -> PlanningResult:
        validate_run_request(request, self.resolver.registry)
        if request["requested_export_target"] != "analysis_report":
            raise ValidationFailure("WGE-3 permits analysis_report output only")
        if len(request["selected_session_ids"]) != 1:
            raise ValidationFailure("WGE-3 diagnostic planning supports one session per run")
        session_id = request["selected_session_ids"][0]
        focus = request.get("focus_role_target")
        if not isinstance(focus, int) or focus not in range(8):
            raise ValidationFailure("Explicit run-specific Focus Role target is required")
        root_seed = request.get("root_seed", request.get("random_seed"))
        if not isinstance(root_seed, int):
            raise ValidationFailure("A deterministic integer root seed is required")
        profile, preset, planning_profile, authority = self.resolver.resolve(
            request["source_profile_id"], request["delivery_preset_id"], session_id
        )
        motif_metadata = _identity_metadata(self.resolver.root)
        sample_rates = {item.get("sample_rate_hz") for item in motif_metadata}
        if len(sample_rates) != 1 or not isinstance(next(iter(sample_rates)), int):
            raise ValidationFailure("Authoritative motif sample rate is unresolved")
        sample_rate_hz = next(iter(sample_rates))
        mode = next(
            item["mode_id"] for item in profile["session_topology"]["sessions"]
            if item["session_id"] == session_id
        )
        macro = {
            "schema_version": "wge.macro_state_plan.v1",
            "macro_state_plan_id": f"session_{session_id:02d}_macro",
            "mode": mode,
            "states": [{
                "state_id": "baseline_active_000",
                "state_category": "neutral_active",
                "start_sample": 0,
                "end_sample_exclusive": request["requested_duration_seconds"] * sample_rate_hz,
                "authority_status": "identity_safe_baseline_representation",
            }],
            "content_hash": "",
        }
        macro["content_hash"] = content_hash(macro)
        planner = MODE_PLANNERS[mode]()
        packet_plan, event_plan, randomness = planner.plan(
            session_id=session_id,
            duration_seconds=request["requested_duration_seconds"],
            sample_rate_hz=sample_rate_hz,
            root_seed=root_seed,
            focus_role_target=focus,
            planning_profile=planning_profile,
            motif_metadata=motif_metadata,
        )
        request_hash = content_hash(request)
        session_plan = {
            "schema_version": "wge.session_plan.v1",
            "session_plan_id": f"session_{session_id:02d}_plan",
            "session_id": session_id,
            "mode": mode,
            "duration_seconds": request["requested_duration_seconds"],
            "duration_samples": request["requested_duration_seconds"] * sample_rate_hz,
            "sample_rate_hz": sample_rate_hz,
            "logical_channel_count": 8,
            "focus_role_target": focus,
            "focus_role_source": "diagnostic_run_request",
            "profile_default": False,
            "macro_state_plan_id": macro["macro_state_plan_id"],
            "packet_count": len(packet_plan["packets"]),
            "event_count": len(event_plan["events"]),
            "packet_plan_path": "packet_plan.json",
            "event_plan_path": "event_plan.json",
            "authority_references": list(authority["files"]),
            "planning_profile_hash": planning_profile["content_hash"],
            "random_seed": randomness["session_seed"],
            "validation_status": "pending",
            "diagnostic_status": "pending",
            "headroom_status": "not_certified_without_waveform_render_and_overlap_sum",
            "content_hash": "",
        }
        if "meso_schedule" in packet_plan:
            session_plan["meso_schedule"] = {
                key: packet_plan["meso_schedule"][key]
                for key in (
                    "enabled", "policy_id", "policy_hash",
                    "scheduler_result_hash", "phrase_state_model_id",
                    "source_scope", "phrase_count", "phrase_active_share",
                    "anti_lattice_validation",
                )
            }
        session_plan["content_hash"] = content_hash(session_plan)
        pack = {
            "schema_version": "wge.session_pack_plan.v1",
            "plan_id": "x_alpha_session_pack_diagnostic",
            "run_request_id": request["request_id"],
            "run_request_hash": request_hash,
            "source_profile_id": profile["profile_id"],
            "source_profile_hash": profile["content_hash"],
            "delivery_preset_id": preset["preset_id"],
            "delivery_preset_hash": preset["content_hash"],
            "selected_session_ids": [session_id],
            "requested_duration_seconds": request["requested_duration_seconds"],
            "sample_rate_hz": sample_rate_hz,
            "channel_convention": "zero_based_0_7",
            "focus_role_mapping": {
                "target_logical_channel": focus,
                "focus_role_source": "diagnostic_run_request",
                "profile_default": False,
                "associated_density_emphasis": True,
                "playback_intensity_changed": False,
                "calibration_changed": False,
            },
            "randomness_policy": randomness,
            "root_seed": root_seed,
            "planning_profile_snapshots": [planning_profile["snapshot_id"]],
            "session_plan_ids": [session_plan["session_plan_id"]],
            "authority_snapshot": authority,
            "provisional_defaults": planning_profile["provisional_defaults"],
            "warnings": ["Tier 2 numeric guidance is diagnostic and non-binding."],
            "executable_for_rendering": False,
            "implementation_phase": "WGE-3",
            "content_hash": "",
        }
        pack["content_hash"] = content_hash(pack)
        from .validation import validate_plans
        validation = validate_plans(
            pack, session_plan, macro, packet_plan, event_plan, motif_metadata
        )
        session_plan["validation_status"] = "passed"
        session_plan["diagnostic_status"] = "ready"
        session_plan["content_hash"] = content_hash(session_plan)
        return PlanningResult(
            request, authority, profile, preset, planning_profile, pack,
            session_plan, macro, packet_plan, event_plan, validation,
        )

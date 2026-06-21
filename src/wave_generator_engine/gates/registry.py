from collections.abc import Iterable, Iterator
from typing import Any

from wave_generator_engine.errors import GateClosedError, ValidationFailure
from .models import Gate, GateAction

SCAFFOLD_GATES = {
    "open_final_test_arrays",
    "mutate_or_replace_frozen_assets",
    "refit_models",
    "default_generated_motifs",
    "exact_replay_through_transform_logic",
    "transform_execution_inside_interchange",
    "hardcoded_channel_5_focus",
    "macro_unit_only_or_required_generation",
    "production_wav_generation",
    "production_upload_json_generation",
    "tier_2_numeric_profiles_as_production_constants",
    "tier_3_reference_research_promoted_to_authority",
    "exact_mode_carrier_control_request",
    "schedule_spectrum_mislabeled_as_carrier",
    "exact_mode_motif_time_scaling",
    "uncertified_time_scaling_range",
    "silent_timing_control_coupling",
    "per_motif_normalization",
    "per_session_normalization",
    "default_output_limiter",
    "playback_intensity_baked_into_wav",
    "fixed_physical_focus_channel",
    "focus_density_role_desynchronization",
    "complex_mode_smooth_envelope_substitution",
    "packet_scheduling_before_required_macro_state_schedule",
    "pulse_pattern_removal_in_standard_mode",
    "unvalidated_24_bit_production_requirement",
    "exact_state_counts_as_universal_script",
    "frozen_asset_mutation_request",
    "missing_provenance_request",
    "unvalidated_motif_source_request",
    "diagnostic_wav_generation",
    "analysis_report_generation",
    "assembled_stereo_wav_pack_generation",
    "session_number_branching",
    "silent_motif_time_scaling",
    "silent_calibration_change",
    "intensity_as_source_normalization",
    "basic_mode_internal_pulse_controls",
}


def _machine_ids(values: Iterable[Any]) -> set[str]:
    return {value for value in values if isinstance(value, str) and value and " " not in value}


class GateRegistry:
    def __init__(self, gates: Iterable[Gate]) -> None:
        self._gates = {gate.gate_id: gate for gate in gates}

    @classmethod
    def from_authority(
        cls,
        handoff: dict[str, Any],
        decisions: dict[str, Any],
        artifacts: list[dict[str, Any]],
    ) -> "GateRegistry":
        required = set(SCAFFOLD_GATES)
        required |= _machine_ids(handoff.get("blocked_behaviors", []))
        for decision in decisions.get("decisions", []):
            required |= _machine_ids(decision.get("blocked_alternatives", []))
        for artifact in artifacts:
            required |= _machine_ids(artifact.get("blocked_use", []))
        gates = [
            Gate(
                gate_id=gate_id,
                description=f"Reject unsafe WGE-0 request: {gate_id.replace('_', ' ')}.",
                authority_source="engine-scaffold-and-interchange",
                default_action=GateAction.REJECT,
                error_code=f"WGE0_GATE_{index:03d}",
            )
            for index, gate_id in enumerate(sorted(required), start=1)
        ]
        registry = cls(gates)
        missing = required - set(registry._gates)
        if missing:
            raise ValidationFailure("Blocked gate coverage is incomplete")
        return registry

    def __len__(self) -> int:
        return len(self._gates)

    def __iter__(self) -> Iterator[Gate]:
        return iter(self._gates.values())

    def reject(self, request_id: str) -> None:
        gate = self._gates.get(request_id)
        if gate is None:
            raise GateClosedError(
                request_id, "WGE0_GATE_UNKNOWN",
                "Unknown requests fail closed in WGE-0",
            )
        raise GateClosedError(gate.gate_id, gate.error_code, gate.description)

    def covers(self, gate_id: str) -> bool:
        return gate_id in self._gates

from dataclasses import dataclass
from typing import Any

from wave_generator_engine.errors import ValidationFailure


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValidationFailure(message)


@dataclass(frozen=True)
class ClosurePolicies:
    calibration: dict[str, Any]
    carrier: dict[str, Any]
    pulse_pattern: dict[str, Any]
    macro_density: dict[str, Any]
    timing: dict[str, Any]

    def validate(self) -> None:
        c = self.calibration
        rules = c["settled_rules"]
        _require(c["authority_tier"] == "tier_1", "Calibration must be Tier 1")
        _require(rules["reference_multiplier"] == 1.1, "Reference multiplier must be 1.1")
        _require(rules["default_playback_intensity"] == 0.80, "Playback intensity must be 0.80")
        _require(rules["playback_intensity_stage"] == "post_calibration", "Intensity must be post-calibration")
        _require(not rules["per_motif_normalization"], "Per-motif normalization is blocked")
        _require(not rules["per_session_normalization"], "Per-session normalization is blocked")
        _require(not rules["default_limiter"], "Default limiter is blocked")
        _require(rules["preserve_relative_amplitude_relationships"], "Relative amplitude must be preserved")
        _require(rules["invalid_headroom_policy"] == "fail_validation", "Invalid headroom must fail")
        _require(rules["focus_role_must_not_change_global_intensity"], "Focus Role must not change intensity")
        _require(c["render_safety"]["internal_intermediate"] == "float64", "Future intermediate must be float64")
        _require(c["render_safety"]["true_peak_ceiling_dbfs"] == -3.0, "Future ceiling must be -3 dBFS")
        _require(c["tier_3_guidance"]["status"] == "pending_target_hardware_validation", "24-bit must remain provisional")

        carrier = self.carrier["settled_rules"]
        _require(not carrier["continuous_carrier_certified"], "Continuous carrier must not be certified")
        _require(carrier["exact_mode"]["carrier_control"] == "locked_not_exposed", "Exact carrier control must be hidden")
        _require(carrier["exact_mode"]["carrier_frequency_hz"] is None, "Exact carrier value must be null")
        _require(carrier["exact_mode"]["motif_internal_timing"] == "immutable", "Exact timing must be immutable")
        _require(not carrier["schedule_spectrum_is_carrier"], "Schedule spectrum is not a carrier")
        scaling = carrier["adjustable_time_scaling"]
        _require(scaling["certificate_required"] and scaling["minimum"] is None and scaling["maximum"] is None, "Time scaling must remain uncertified")
        _require(scaling["schedule_independence_required"], "Scheduling must remain independent")

        pulse = self.pulse_pattern["settled_rules"]
        _require(not pulse["invariant"], "Pulse Pattern must be mode-specific")
        _require(pulse["basic_mode_exposure"] == "hidden_validated_profiles", "Basic must hide Pulse Pattern internals")
        _require(pulse["advanced_mode_exposure"] == "future_bounded_controls", "Advanced controls must remain future-only")
        _require(pulse["complete_removal"] == "experimental_only", "Removal must be experimental-only")
        _require(pulse["timing_independent_of_motif_internal_timing"], "Pulse timing must not scale motifs")
        _require(pulse["must_not_change_render_calibration"], "Pulse changes must not change calibration")
        _require(pulse["defaults_are_mode_data_not_session_branches"], "Pulse defaults must be mode data")

        macro = self.macro_density
        mrules = macro["settled_rules"]
        _require(mrules["complex_mode_requires_explicit_macro_state_schedule"], "Complex Mode needs macro states")
        _require(mrules["stage_order"] == ["macro_state_schedule", "packet_schedule", "event_schedule"], "Macro stage order is invalid")
        _require(set(mrules["required_states"]) == {"occupied_plateau", "deep_gap", "transition_low"}, "Macro states are incomplete")
        _require(mrules["local_jitter"] == "bounded_inside_occupied_states", "Local jitter rule is invalid")
        _require(not mrules["smooth_wandering_envelope_conforming"], "Smooth envelope substitution is blocked")
        _require(bool(mrules["required_diagnostics"]), "Macro diagnostics must be registered")
        _require(macro["tier_2_complex_reference"]["universal_script"] is False, "Tier 2 counts are not universal")

        timing = self.timing
        _require(timing["core_rule"] == "Independent concepts must never be silently linked.", "Dependency core rule changed")
        couplings = {tuple(x) for x in timing["required_couplings"]}
        independence = {tuple(x) for x in timing["required_independence"]}
        _require(("focus_role_mapping", "density_emphasis") in couplings, "Focus Role bundle is missing")
        _require(("playback_intensity", "physical_focus_target") in independence, "Intensity must remain independent")
        _require(("render_calibration", "physical_channel_mapping") in independence, "Calibration must remain independent")

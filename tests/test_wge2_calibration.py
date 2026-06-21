import numpy as np

from wave_generator_engine.calibration.policy import load_calibration_policy
from wave_generator_engine.calibration.preflight import (
    FINAL_HEADROOM_STATUS, run_calibration_preflight,
)
from wave_generator_engine.motifs.profile_integration import validate_profile_integration


def test_calibration_policy_binding() -> None:
    policy = load_calibration_policy()
    assert policy.reference_multiplier == 1.1
    assert policy.default_playback_intensity == 0.80
    assert policy.playback_intensity_stage == "post_calibration"
    assert not policy.per_motif_normalization
    assert not policy.per_session_normalization
    assert not policy.default_limiter
    assert policy.preserve_relative_amplitude_relationships
    assert policy.internal_intermediate == "float64"
    assert policy.true_peak_ceiling_dbfs == -3.0
    assert policy.reserve_db == 3.0
    assert policy.delivery_24_bit_status == "pending_target_hardware_validation"


def test_preflight_is_diagnostic_and_preserves_sources(real_motif_bank) -> None:
    before = [item.samples.copy() for item in real_motif_bank.records()]
    report = run_calibration_preflight(real_motif_bank)
    assert report["motif_count"] == 84
    assert report["diagnostic_intermediate"] == "float64"
    assert report["relative_amplitude_preserved"]
    assert report["source_values_unchanged"]
    assert not report["playback_intensity_applied"]
    assert not report["normalization_applied"]
    assert not report["limiter_applied"]
    assert not report["focus_role_applied"]
    assert report["final_render_headroom_status"] == FINAL_HEADROOM_STATUS
    assert not report["render_certification_claimed"]
    assert all(np.array_equal(item.samples, saved)
               for item, saved in zip(real_motif_bank.records(), before))


def test_x_alpha_profile_integration_remains_non_executable(real_motif_bank) -> None:
    result = validate_profile_integration(
        real_motif_bank, load_calibration_policy()
    )
    assert result["valid"] and result["exact_access_only"]
    assert result["locked"] and not result["executable"]
    assert not result["carrier_control_exposed"]
    assert not result["motif_time_scaling_available"]
    assert not result["session_plan_created"]

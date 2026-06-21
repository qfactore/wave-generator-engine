import copy
import json

import pytest

from wave_generator_engine.config import AUTHORITY_ARTIFACT_SCHEMAS
from wave_generator_engine.errors import ValidationFailure
from wave_generator_engine.interchange.closure_policies import ClosurePolicies


def policies(root) -> ClosurePolicies:
    return ClosurePolicies(*[
        json.loads((root / path).read_text())
        for path in AUTHORITY_ARTIFACT_SCHEMAS
    ])


def test_all_binding_closure_contracts(interchange_root) -> None:
    value = policies(interchange_root)
    value.validate()
    assert value.calibration["settled_rules"]["reference_multiplier"] == 1.1
    assert value.calibration["settled_rules"]["playback_intensity_stage"] == "post_calibration"
    assert value.carrier["settled_rules"]["exact_mode"]["motif_internal_timing"] == "immutable"
    assert value.pulse_pattern["settled_rules"]["basic_mode_exposure"] == "hidden_validated_profiles"
    assert value.macro_density["settled_rules"]["stage_order"][0] == "macro_state_schedule"
    assert ["focus_role_mapping", "density_emphasis"] in value.timing["required_couplings"]


@pytest.mark.parametrize("index,mutation", [
    (0, ("settled_rules", "per_motif_normalization", True)),
    (0, ("settled_rules", "per_session_normalization", True)),
    (0, ("settled_rules", "default_limiter", True)),
    (1, ("settled_rules", "schedule_spectrum_is_carrier", True)),
    (2, ("settled_rules", "complete_removal", "standard")),
    (3, ("settled_rules", "smooth_wandering_envelope_conforming", True)),
])
def test_blocked_policy_drift_fails(interchange_root, index, mutation) -> None:
    value = policies(interchange_root)
    artifacts = [copy.deepcopy(x) for x in (
        value.calibration, value.carrier, value.pulse_pattern,
        value.macro_density, value.timing,
    )]
    parent, key, replacement = mutation
    artifacts[index][parent][key] = replacement
    with pytest.raises(ValidationFailure):
        ClosurePolicies(*artifacts).validate()


def test_24_bit_remains_provisional(interchange_root) -> None:
    assert policies(interchange_root).calibration["tier_3_guidance"]["status"] == \
        "pending_target_hardware_validation"


def test_exact_state_counts_are_reference_only(interchange_root) -> None:
    assert policies(interchange_root).macro_density["tier_2_complex_reference"]["universal_script"] is False

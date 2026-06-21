from pathlib import Path

ENGINE_ROOT = Path(__file__).resolve().parents[2]
INTERCHANGE_ENV = "WAVE_GEN_INTERCHANGE_DIR"
FORBIDDEN_TERMS_ENV = "WGE_FORBIDDEN_TERMS"
EXPECTED_FROZEN_SHA256 = "7e248804420fdcc75713fd3c232f6c97f5581d01be83526f0ea5770002fc29dd"
EXPECTED_IDENTITY_COUNT = 84

CORE_HANDOFF_PATHS = (
    "handoff/handoff_manifest.json",
    "handoff/WAVE_GENERATOR_ENGINE_HANDOFF_PACK.md",
    "handoff/ENGINE_CONFORMANCE_CHECKLIST.md",
    "handoff/BLOCKED_BEHAVIORS.md",
    "handoff/VALIDATION_COMMANDS.md",
    "handoff/PRE_ENGINE_ANALYSIS_HANDOFF.md",
    "handoff/CALIBRATION_HANDOFF.md",
    "manifests/canonical_interchange_manifest.json",
    "manifests/decision_registry.json",
    "manifests/source_artifact_manifest.json",
    "manifests/source_hashes.json",
    "bank/frozen_assets/frozen_motif_identity_index.json",
    "bank/fixtures/fixture_catalog.json",
    "bank/calibration/x_alpha_reference_calibration_v1.json",
    "bank/grammar/carrier_frequency_policy_v1.json",
    "bank/grammar/pulse_pattern_grammar_v1.json",
    "bank/grammar/macro_density_state_model_v1.json",
    "bank/grammar/timing_dependency_policy_v1.json",
    "reports/wg_i8_readiness_report.json",
    "reports/WG_I8_READINESS_REPORT.md",
)

AUTHORITY_ARTIFACT_SCHEMAS = {
    "bank/calibration/x_alpha_reference_calibration_v1.json":
        "schemas/x_alpha_reference_calibration.schema.json",
    "bank/grammar/carrier_frequency_policy_v1.json":
        "schemas/carrier_frequency_policy.schema.json",
    "bank/grammar/pulse_pattern_grammar_v1.json":
        "schemas/pulse_pattern_grammar.schema.json",
    "bank/grammar/macro_density_state_model_v1.json":
        "schemas/macro_density_state_model.schema.json",
    "bank/grammar/timing_dependency_policy_v1.json":
        "schemas/timing_dependency_policy.schema.json",
}

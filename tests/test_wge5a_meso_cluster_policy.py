import hashlib
import json
from pathlib import Path

from jsonschema import Draft202012Validator

from wave_generator_engine.config import ENGINE_ROOT
from wave_generator_engine.export_contract.diagnostic import _tree_hash
from wave_generator_engine.interchange.discovery import discover_interchange
from wave_generator_engine.profiles.hashing import validate_content_hash
from wave_generator_engine.qualification.authority import QualificationAuthority

ROOT = Path(__file__).resolve().parents[1]
POLICY_PATH = ROOT / "policies/meso_cluster_rhythm_policy_v1.json"
AUDIT_PATH = ROOT / "reports/wge5a_meso_cluster_rhythm_audit.json"
RUN = ROOT / "runs/latest"


def _json(path: Path) -> dict:
    return json.loads(path.read_text())


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_policy_schema_and_content_hash_validate() -> None:
    policy = _json(POLICY_PATH)
    schema = _json(ROOT / "schemas/meso_cluster_rhythm_policy.schema.json")
    Draft202012Validator(schema).validate(policy)
    assert validate_content_hash(policy)
    assert policy["executable"] is False
    assert policy["wge5b_meso_cluster_implementation_authorized"] is True
    assert policy["authorization_blockers"] == []


def test_authority_references_are_permitted_and_hash_verified() -> None:
    authority = QualificationAuthority()
    inventory = {item.artifact_id: item for item in authority.inventory()}
    inventory["phase5e_hum_throb_contract"] = authority.direct(
        "phase5e_hum_throb_contract",
        "coordinated_dimensions|strongest_supported_diagnostic",
        "shared_hum_throb_contract",
    )
    inventory["phase5l_hum_putput_unit_interpretation"] = authority.direct(
        "phase5l_hum_putput_unit_interpretation",
        "candidate_evidence|summary",
        "baseline_sessions_1_4",
    )
    inventory["phase5l_unit_grammar_audit_report"] = authority.direct(
        "phase5l_unit_grammar_audit_report",
        "training/validation event metadata and generated-file inventory",
        "direct_session_1_and_baseline_sessions_1_4",
    )
    policy = _json(POLICY_PATH)
    for record in policy["authority_references"]:
        artifact_id = record["artifact_id"]
        assert artifact_id in inventory
        reference = inventory[artifact_id]
        assert reference.path.is_file()
        assert reference.authority_tier == record["authority_tier"]
        assert reference.classification_status == "include"
    assert not _json(AUDIT_PATH)["blocked_final_test_accessed"]


def test_policy_uses_state_model_and_source_supported_cluster_evidence() -> None:
    policy = _json(POLICY_PATH)
    assert policy["cluster_detection"]["threshold_samples"] is None
    assert policy["cluster_detection"]["model_type"] == \
        "probabilistic_recurrent_interval_phrase_state"
    assert policy["cluster_size_distribution"]["target_quantiles_packets"]["median"] == 6
    assert policy["between_cluster_gap_model"]["target_quantiles_seconds"]["median"] == \
        0.7834687499999999
    assert policy["phrase_selection_weights"]["weights"]["phrase_active"] == \
        0.39755351681957185
    assert policy["overlap_constraints"]["maximum_concurrency"] == 3
    assert policy["source_packet_start_population"]["session_1"]["packet_start_count"] == 752
    assert policy["source_packet_start_population"]["baseline_sessions_1_4"][
        "packet_start_count"
    ] == 6112


def test_policy_preserves_grammar_and_blocks_carrier_and_fixed_lattice() -> None:
    policy = _json(POLICY_PATH)
    blocked = set(policy["blocked_interpretations"])
    assert "continuous_carrier_without_direct_permitted_evidence" in blocked
    assert "global_fixed_packet_lattice" in blocked
    assert "canonical_packet_grammar_replacement" in blocked
    assert policy["channel_coupling_rules"]["preserve_canonical_packet_grammar"]
    assert not policy["transition_rules"]["fixed_global_rhythm_allowed"]


def test_audit_records_generated_plan_metrics_without_modifying_plan() -> None:
    audit = _json(AUDIT_PATH)
    assert validate_content_hash(audit)
    generated = audit["generated_plan_comparison"]
    assert generated["packet_count"] == 149
    assert generated["event_count"] == 960
    assert generated["packet_density_1s"]["zero_bins"] == 0
    assert generated["event_density_5s"]["coefficient_of_variation"] < 0.08
    assert generated["maximum_concurrency"] == 2
    assert audit["hum_put_put_interpretation"]["classification"] == \
        "repeated packet phrase"
    assert not audit["hum_put_put_interpretation"]["continuous_component_supported"]
    assert audit["generated_plan_comparison"]["phrase_state_cluster_count"] == 0
    assert audit["generated_plan_comparison"]["phrase_recurrence_comparison"] == \
        "outside_source_reference"
    assert audit["authorization"]["wge5b_meso_cluster_implementation_authorized"]


def test_protected_plan_render_contract_and_wav_hashes_are_unchanged() -> None:
    snapshot = _json(RUN / "diagnostic_export/export_authority_snapshot.json")
    for relative, expected in snapshot["core_plan_hashes"].items():
        document = _json(RUN / relative)
        assert document["content_hash"] == expected
        assert validate_content_hash(document)
    assert _sha256(RUN / "render_audit/render_receipt.json") == \
        "ac2ea1412c6b87c0b6488aebbbdbc111a372f51fe8108794b2e790b72ec3f3f9"
    wav_hashes = [
        "9c5ed5994f9e4d8ec15dac91851f788508df106185b4816ddc11054ae2170747",
        "28472051eea75634ef0dae74eb3cab7f214b09c47e89e35487f7168113057d9c",
        "4954c3e6ac8e01fed500b85bcdd46e4cb29dc62e336787aed7ce5c9df726d9e4",
        "9b1dbdf3eb955c80bd37203c8ef6d0bfabbeee551ed84e73460143863ec6df61",
    ]
    files = sorted((RUN / "diagnostic_export/files").glob("*.wav"))
    assert [_sha256(path) for path in files] == wav_hashes


def test_interchange_tree_and_engine_version_are_unchanged() -> None:
    interchange = discover_interchange(ENGINE_ROOT, None)
    assert _tree_hash(interchange) == \
        "a825c3d4b2630a3d932a535def46ffacb4c2b569f87d151d437e1ef0756cd17a"
    assert _json(AUDIT_PATH)["engine_version"] == "0.5.1"

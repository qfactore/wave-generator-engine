import copy
import inspect
import json
from pathlib import Path

import pytest

from wave_generator_engine.diagnostics.service import diagnostic_arrays, generate_diagnostics
from wave_generator_engine.errors import ValidationFailure
from wave_generator_engine.planning.service import PlanningService
from wave_generator_engine.planning.validation import (
    validate_channel_grammar,
    validate_plans,
)

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def result():
    request = json.loads(
        (ROOT / "examples/run_requests/x_alpha_session1_diagnostic_60s.json").read_text()
    )
    return PlanningService().build(request)


def _revalidate(result, packet_plan=None, event_plan=None):
    index = json.loads(
        (ROOT.parent / "wave-gen-interchange/bank/frozen_assets/"
         "frozen_motif_identity_index.json").read_text()
    )
    return validate_plans(
        result.session_pack_plan, result.session_plan, result.macro_state_plan,
        packet_plan or result.packet_plan, event_plan or result.event_plan,
        index["motifs"],
    )


def test_fixed_half_second_packet_lattice_is_rejected(result) -> None:
    packets = copy.deepcopy(result.packet_plan)
    for index, packet in enumerate(packets["packets"]):
        packet["onset_sample"] = index * 24000
    with pytest.raises(ValidationFailure, match="packet_timing_variance"):
        _revalidate(result, packet_plan=packets)


def test_universal_fixed_25ms_continuations_are_rejected(result) -> None:
    packets = copy.deepcopy(result.packet_plan)
    events = copy.deepcopy(result.event_plan)
    by_id = {item["event_id"]: item for item in events["events"]}
    for packet in packets["packets"]:
        selected = [by_id[item] for item in packet["event_ids"]]
        packet["continuation_spacings_samples"] = [1200] * (len(selected) - 1)
        for index, event in enumerate(selected):
            event["onset_sample"] = packet["onset_sample"] + index * 1200
            event["end_sample_exclusive"] = event["onset_sample"] + event["duration_samples"]
    with pytest.raises(ValidationFailure, match="continuation_timing_policy"):
        _revalidate(result, packet_plan=packets, event_plan=events)


@pytest.mark.parametrize("grammar", [
    "clean_plus_one_sweep", "sweep_with_repeats", "partial_sweep",
    "scattered_packet", "two_impulse_burst", "three_impulse_burst",
])
def test_invalid_singleton_grammar_is_rejected(grammar: str) -> None:
    with pytest.raises(ValidationFailure, match="unit_grammar_structure"):
        validate_channel_grammar({"unit_grammar": grammar, "channel_sequence": [2]})


@pytest.mark.parametrize(("grammar", "channels"), [
    ("one_impulse_burst", [3]),
    ("two_impulse_burst", [3, 3]),
    ("three_impulse_burst", [3, 3, 3]),
    ("clean_plus_one_sweep", [2, 3, 4, 5, 6, 7, 0, 1]),
    ("sweep_with_repeats", [2, 3, 4, 4, 5, 6]),
    ("partial_sweep", [6, 7, 0, 1]),
])
def test_valid_canonical_structures_pass(grammar: str, channels: list[int]) -> None:
    validate_channel_grammar({"unit_grammar": grammar, "channel_sequence": channels})


def test_generated_timing_and_pulse_realisation(result) -> None:
    packets = result.packet_plan["packets"]
    intervals = [
        second["onset_sample"] - first["onset_sample"]
        for first, second in zip(packets, packets[1:])
    ]
    assert len(set(intervals)) > 1
    spacings = []
    for packet in packets:
        validate_channel_grammar(packet)
        assert packet["continuation_count"] == len(packet["event_ids"]) - 1
        assert packet["pulse_pattern_present"] == (len(packet["event_ids"]) > 1)
        spacings.extend(packet["continuation_spacings_samples"])
    assert len(set(spacings)) > 1


def test_different_seed_changes_packet_timing(result) -> None:
    changed = copy.deepcopy(result.run_request)
    changed["root_seed"] += 1
    changed["request_id"] = "wge3r_changed_seed"
    other = PlanningService().build(changed)
    first = [item["onset_sample"] for item in result.packet_plan["packets"]]
    second = [item["onset_sample"] for item in other.packet_plan["packets"]]
    assert first != second


def test_random_trace_names_are_stage_accurate(result) -> None:
    trace = result.event_plan["events"][0]["random_selection_trace"]
    assert "packet_seed" not in trace
    assert "packet_stage_seed" in trace
    assert {"packet_index", "unit_index"} <= set(trace)


def test_diagnostic_source_data_and_semantics(result, tmp_path: Path) -> None:
    data = diagnostic_arrays(result)
    timeline = data["timeline_overview"]
    assert timeline["x_axis"] == "seconds"
    assert timeline["y_axis"] == "logical_channel_0_7"
    assert timeline["packet_starts"] and timeline["continuations"]
    focus = data["focus_non_focus_comparison"]
    assert focus["focus_series_label"].startswith("Focus channel")
    assert focus["non_focus_series_label"] == "Non-focus channel mean"
    assert len(focus["focus_event_count"]) == len(focus["non_focus_mean_event_count"])
    assert focus["focus_to_non_focus_mean_ratio"] > 0
    assert data["event_gain_distribution"] == {"1.0": len(result.event_plan["events"])}
    assert len(set(data["packet_interval_over_time"]["interval_seconds"])) > 1
    manifest = generate_diagnostics(result, tmp_path)
    for figure in manifest["figure_files"]:
        assert (tmp_path / figure).stat().st_size > 1000
    for raw in manifest["raw_files"]:
        assert (tmp_path / raw).stat().st_size > 0


def test_diagnostics_do_not_access_waveform_samples() -> None:
    source = inspect.getsource(diagnostic_arrays)
    assert "FrozenMotifBank" not in source
    assert "np.load" not in source
    assert '["samples"]' not in source

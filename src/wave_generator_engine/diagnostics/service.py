import csv
import json
import os
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

os.environ.setdefault("MPLCONFIGDIR", "/tmp/wge-matplotlib-cache")
os.environ.setdefault("XDG_CACHE_HOME", "/tmp/wge-cache")

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from wave_generator_engine.profiles.hashing import content_hash

LABEL = "Diagnostic plan metadata only — no waveform rendered"
DIAGNOSTIC_NAMES = (
    "timeline_overview", "macro_state_timeline", "macro_density_over_time",
    "meso_density_over_time", "packet_density_over_time",
    "event_density_over_time", "channel_activity_over_time",
    "channel_occupancy", "focus_role_activity",
    "focus_non_focus_comparison", "motif_usage",
    "motif_repetition_distance", "unit_grammar_usage",
    "channel_transition_matrix", "pulse_pattern_prevalence",
    "continuation_count_distribution", "packet_span_distribution",
    "event_gain_distribution",
)


def _write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def _figure(path: Path, title: str, x: np.ndarray, y: np.ndarray) -> None:
    figure, axis = plt.subplots(figsize=(8, 3))
    if y.ndim == 2:
        image = axis.imshow(y, aspect="auto", origin="lower")
        figure.colorbar(image, ax=axis)
    else:
        axis.plot(x, y)
    axis.set_title(title)
    axis.set_xlabel(LABEL)
    figure.tight_layout()
    figure.savefig(path, dpi=100)
    plt.close(figure)


def diagnostic_arrays(result) -> dict[str, Any]:
    events = result.event_plan["events"]
    packets = result.packet_plan["packets"]
    rate = result.session_plan["sample_rate_hz"]
    duration = result.session_plan["duration_seconds"]
    focus = result.session_plan["focus_role_target"]
    bins = np.arange(duration + 1)
    event_seconds = np.array([item["onset_sample"] / rate for item in events])
    packet_seconds = np.array([item["onset_sample"] / rate for item in packets])
    event_density, _ = np.histogram(event_seconds, bins=bins)
    packet_density, _ = np.histogram(packet_seconds, bins=bins)
    channel_activity = np.zeros((8, duration), dtype=int)
    for event in events:
        index = min(duration - 1, event["onset_sample"] // rate)
        channel_activity[event["logical_channel"], index] += 1
    transitions = np.zeros((8, 8), dtype=int)
    for first, second in zip(events, events[1:]):
        transitions[first["logical_channel"], second["logical_channel"]] += 1
    motif_counts = Counter(item["motif_id"] for item in events)
    grammar_counts = Counter(item["unit_grammar"] for item in packets)
    continuation_counts = Counter(str(item["continuation_count"]) for item in packets)
    repetition_distances = []
    last_seen: dict[str, int] = {}
    for index, event in enumerate(events):
        if event["motif_id"] in last_seen:
            repetition_distances.append(index - last_seen[event["motif_id"]])
        last_seen[event["motif_id"]] = index
    packet_spans = []
    by_id = {item["event_id"]: item for item in events}
    for packet in packets:
        selected = [by_id[item] for item in packet["event_ids"]]
        packet_spans.append(
            max((item["end_sample_exclusive"] for item in selected), default=packet["onset_sample"])
            - packet["onset_sample"]
        )
    focus_activity = channel_activity[focus]
    non_focus_activity = np.sum(channel_activity, axis=0) - focus_activity
    data = {
        "density_definitions": {
            "event_density_over_time": "event onsets per fixed one-second bin",
            "packet_density_over_time": "packet onsets per fixed one-second bin",
            "macro_density_over_time": "active macro-state occupancy per one-second bin",
            "meso_density_over_time": "events per fixed five-second bin",
            "channel_activity_over_time": "event onsets by logical channel per one-second bin",
        },
        "timeline_overview": {"onset_seconds": event_seconds.tolist(),
                              "channels": [item["logical_channel"] for item in events]},
        "macro_state_timeline": {"seconds": list(range(duration)), "active": [1] * duration},
        "macro_density_over_time": {"seconds": list(range(duration)), "active_state_count": [1] * duration},
        "meso_density_over_time": {
            "bin_start_seconds": list(range(0, duration, 5)),
            "event_count": [int(sum(event_density[i:i + 5])) for i in range(0, duration, 5)],
        },
        "packet_density_over_time": {"seconds": list(range(duration)), "packet_count": packet_density.tolist()},
        "event_density_over_time": {"seconds": list(range(duration)), "event_count": event_density.tolist()},
        "channel_activity_over_time": {"seconds": list(range(duration)), "matrix": channel_activity.tolist()},
        "channel_occupancy": dict(Counter(str(item["logical_channel"]) for item in events)),
        "focus_role_activity": {"seconds": list(range(duration)), "event_count": focus_activity.tolist()},
        "focus_non_focus_comparison": {
            "seconds": list(range(duration)), "focus": focus_activity.tolist(),
            "non_focus": non_focus_activity.tolist(),
        },
        "motif_usage": dict(sorted(motif_counts.items())),
        "motif_repetition_distance": repetition_distances,
        "unit_grammar_usage": dict(sorted(grammar_counts.items())),
        "channel_transition_matrix": transitions.tolist(),
        "pulse_pattern_prevalence": {
            "with_continuations": sum(item["continuation_count"] > 0 for item in packets),
            "without_continuations": sum(item["continuation_count"] == 0 for item in packets),
        },
        "continuation_count_distribution": dict(sorted(continuation_counts.items())),
        "packet_span_distribution": packet_spans,
        "event_gain_distribution": dict(Counter(str(item["relative_event_gain"]) for item in events)),
    }
    return data


def generate_diagnostics(result, output_dir: Path) -> dict[str, Any]:
    raw = output_dir / "raw"
    figures = output_dir / "figures"
    raw.mkdir(parents=True, exist_ok=True)
    figures.mkdir(parents=True, exist_ok=True)
    data = diagnostic_arrays(result)
    for name in ("density_definitions", *DIAGNOSTIC_NAMES):
        _write_json(raw / f"{name}.json", data[name])
    with (raw / "event_density_over_time.csv").open("w", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(["second", "event_count"])
        writer.writerows(zip(
            data["event_density_over_time"]["seconds"],
            data["event_density_over_time"]["event_count"],
        ))
    with (raw / "channel_activity_over_time.csv").open("w", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(["logical_channel", *range(result.session_plan["duration_seconds"])])
        for channel, row in enumerate(data["channel_activity_over_time"]["matrix"]):
            writer.writerow([channel, *row])
    for name in DIAGNOSTIC_NAMES:
        value = data[name]
        if name == "channel_transition_matrix":
            y = np.asarray(value)
            x = np.arange(y.shape[1])
        elif name == "channel_activity_over_time":
            y = np.asarray(value["matrix"])
            x = np.arange(y.shape[1])
        elif isinstance(value, dict) and "seconds" in value:
            x = np.asarray(value["seconds"])
            key = next(key for key in value if key != "seconds")
            y = np.asarray(value[key])
        elif isinstance(value, dict):
            x = np.arange(len(value))
            y = np.asarray(list(value.values()), dtype=float)
        else:
            y = np.asarray(value if value else [0], dtype=float)
            x = np.arange(len(y))
        _figure(figures / f"{name}.png", name.replace("_", " ").title(), x, y)
    manifest = {
        "schema_version": "wge.diagnostic_manifest.v1",
        "manifest_id": "session_01_diagnostics",
        "label": LABEL,
        "raw_files": [
            *[f"raw/{name}.json" for name in ("density_definitions", *DIAGNOSTIC_NAMES)],
            "raw/event_density_over_time.csv",
            "raw/channel_activity_over_time.csv",
        ],
        "figure_files": [f"figures/{name}.png" for name in DIAGNOSTIC_NAMES],
        "waveform_access_required": False,
        "content_hash": "",
    }
    manifest["content_hash"] = content_hash(manifest)
    _write_json(output_dir / "diagnostic_manifest.json", manifest)
    return manifest

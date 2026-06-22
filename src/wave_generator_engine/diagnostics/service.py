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
    "packet_interval_over_time", "packet_interval_distribution",
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


def _figure(path: Path, name: str, value: Any, focus: int) -> None:
    figure, axis = plt.subplots(figsize=(8, 3))
    title = name.replace("_", " ").title()
    if name == "timeline_overview":
        starts = np.asarray(value["packet_starts"])
        continuations = np.asarray(value["continuations"])
        if starts.size:
            axis.scatter(starts[:, 0], starts[:, 1], marker="s", s=16, label="Packet start")
        if continuations.size:
            axis.scatter(continuations[:, 0], continuations[:, 1], marker=".", s=12,
                         label="Continuation")
        axis.axhspan(focus - 0.4, focus + 0.4, color="gold", alpha=0.18,
                     label=f"Focus Role channel {focus}")
        axis.set_xlabel("Time (seconds)")
        axis.set_ylabel("Logical channel")
        axis.set_yticks(range(8))
        axis.legend(loc="upper right", fontsize=7)
    elif name == "focus_non_focus_comparison":
        axis.plot(value["bin_start_seconds"], value["focus_event_count"],
                  label=f"Focus channel {focus}")
        axis.plot(value["bin_start_seconds"], value["non_focus_mean_event_count"],
                  label="Non-focus channel mean")
        axis.set_xlabel(f"Time (seconds; {value['bin_width_seconds']} s bins)")
        axis.set_ylabel("Event onsets")
        axis.legend()
        title += f" (ratio {value['focus_to_non_focus_mean_ratio']:.3f})"
    elif name in {
        "unit_grammar_usage", "pulse_pattern_prevalence",
        "continuation_count_distribution", "motif_usage", "event_gain_distribution",
    }:
        labels = list(value)
        axis.bar(range(len(labels)), list(value.values()))
        axis.set_xticks(range(len(labels)))
        axis.set_xticklabels(labels, rotation=45, ha="right", fontsize=7)
        axis.set_ylabel("Count")
        axis.set_xlabel("Category")
    elif name == "channel_transition_matrix":
        y = np.asarray(value)
        image = axis.imshow(y, aspect="auto", origin="lower")
        figure.colorbar(image, ax=axis)
        axis.set_xlabel("Destination channel")
        axis.set_ylabel("Source channel")
    elif name == "channel_activity_over_time":
        y = np.asarray(value["matrix"])
        image = axis.imshow(y, aspect="auto", origin="lower")
        figure.colorbar(image, ax=axis)
        axis.set_xlabel("Time bin (seconds)")
        axis.set_ylabel("Logical channel")
    elif name == "packet_interval_over_time":
        axis.plot(value["packet_index"], value["interval_seconds"], marker=".", linewidth=1)
        axis.set_xlabel("Packet index")
        axis.set_ylabel("Interval (seconds)")
    elif name == "packet_interval_distribution":
        axis.hist(value["interval_seconds"], bins=value["bin_count"])
        axis.set_xlabel("Packet interval (seconds)")
        axis.set_ylabel("Count")
    else:
        if isinstance(value, dict):
            x_key = next((key for key in (
                "seconds", "bin_start_seconds", "packet_index"
            ) if key in value), None)
            if x_key is not None:
                y_key = next(key for key in value if key not in {
                    x_key, "bin_width_seconds", "definition"
                })
                axis.plot(value[x_key], value[y_key])
                axis.set_xlabel(x_key.replace("_", " ").title())
                axis.set_ylabel(y_key.replace("_", " ").title())
            else:
                axis.plot(list(value.values()))
        else:
            axis.plot(value if value else [0])
        if not axis.get_xlabel():
            axis.set_xlabel("Diagnostic index")
    axis.set_title(f"{title} — no waveform rendered")
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
    packet_intervals = np.diff(packet_seconds)
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
    non_focus_activity = (np.sum(channel_activity, axis=0) - focus_activity) / 7
    focus_ratio = float(focus_activity.sum() / non_focus_activity.sum()) \
        if non_focus_activity.sum() else 0.0
    packet_starts = [
        [item["onset_sample"] / rate, item["logical_channel"]]
        for item in events if item["pulse_role"] == "packet_start"
    ]
    continuations = [
        [item["onset_sample"] / rate, item["logical_channel"]]
        for item in events if item["pulse_role"] == "packet_continuation"
    ]
    data = {
        "density_definitions": {
            "event_density_over_time": "event onsets per fixed one-second bin",
            "packet_density_over_time": "packet onsets per fixed one-second bin",
            "packet_interval_over_time": "successive packet-onset differences in seconds",
            "packet_interval_distribution": "successive packet-onset differences; 12 equal-width bins",
            "macro_density_over_time": "active macro-state occupancy per one-second bin",
            "meso_density_over_time": "events per fixed five-second bin",
            "channel_activity_over_time": "event onsets by logical channel per one-second bin",
        },
        "timeline_overview": {
            "x_axis": "seconds", "y_axis": "logical_channel_0_7",
            "packet_starts": packet_starts, "continuations": continuations,
            "focus_role_channel": focus,
        },
        "macro_state_timeline": {"seconds": list(range(duration)), "active": [1] * duration},
        "macro_density_over_time": {"seconds": list(range(duration)), "active_state_count": [1] * duration},
        "meso_density_over_time": {
            "bin_start_seconds": list(range(0, duration, 5)),
            "event_count": [int(sum(event_density[i:i + 5])) for i in range(0, duration, 5)],
        },
        "packet_density_over_time": {"seconds": list(range(duration)), "packet_count": packet_density.tolist()},
        "packet_interval_over_time": {
            "packet_index": list(range(1, len(packets))),
            "interval_seconds": packet_intervals.tolist(),
        },
        "packet_interval_distribution": {
            "interval_seconds": packet_intervals.tolist(), "bin_count": 12,
        },
        "event_density_over_time": {"seconds": list(range(duration)), "event_count": event_density.tolist()},
        "channel_activity_over_time": {"seconds": list(range(duration)), "matrix": channel_activity.tolist()},
        "channel_occupancy": dict(Counter(str(item["logical_channel"]) for item in events)),
        "focus_role_activity": {"seconds": list(range(duration)), "event_count": focus_activity.tolist()},
        "focus_non_focus_comparison": {
            "bin_start_seconds": list(range(duration)),
            "bin_width_seconds": 1,
            "focus_series_label": f"Focus channel {focus}",
            "non_focus_series_label": "Non-focus channel mean",
            "focus_event_count": focus_activity.tolist(),
            "non_focus_mean_event_count": non_focus_activity.tolist(),
            "focus_to_non_focus_mean_ratio": focus_ratio,
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
        _figure(
            figures / f"{name}.png", name, data[name],
            result.session_plan["focus_role_target"],
        )
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

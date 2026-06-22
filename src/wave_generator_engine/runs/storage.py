import csv
import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any

from wave_generator_engine.config import ENGINE_ROOT
from wave_generator_engine.diagnostics.service import generate_diagnostics
from wave_generator_engine.errors import ValidationFailure
from wave_generator_engine.planning.service import PlanningService
from wave_generator_engine.profiles.hashing import content_hash


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _safe_id(value: str) -> str:
    if not value or any(char not in "abcdefghijklmnopqrstuvwxyz0123456789-_" for char in value):
        raise ValidationFailure("Saved run ID is unsafe")
    return value


class RunStorage:
    def __init__(self, root: Path | None = None) -> None:
        self.root = root or ENGINE_ROOT / "runs"

    def write_latest(self, result) -> Path:
        self.root.mkdir(parents=True, exist_ok=True)
        temp = Path(tempfile.mkdtemp(prefix=".latest-", dir=self.root))
        try:
            self._write_run(temp, result)
            target = self.root / "latest"
            backup = self.root / ".latest-old"
            if backup.exists():
                shutil.rmtree(backup)
            if target.exists():
                os.replace(target, backup)
            os.replace(temp, target)
            if backup.exists():
                shutil.rmtree(backup)
            return target
        except Exception:
            if temp.exists():
                shutil.rmtree(temp)
            raise

    def write_saved(self, run_id: str, result, overwrite: bool = False) -> Path:
        safe = _safe_id(run_id)
        target = self.root / "saved" / safe
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists() and not overwrite:
            raise ValidationFailure("Saved run already exists; use overwrite explicitly")
        temp = Path(tempfile.mkdtemp(prefix=f".{safe}-", dir=target.parent))
        try:
            self._write_run(temp, result)
            if target.exists():
                shutil.rmtree(target)
            os.replace(temp, target)
            return target
        except Exception:
            if temp.exists():
                shutil.rmtree(temp)
            raise

    def _write_run(self, target: Path, result) -> None:
        session_dir = target / f"sessions/session_{result.session_plan['session_id']:02d}"
        diagnostics_dir = target / "diagnostics"
        session_dir.mkdir(parents=True, exist_ok=True)
        _write_json(target / "request.json", result.run_request)
        _write_json(target / "authority_snapshot.json", result.authority_snapshot)
        _write_json(target / "source_profile_snapshot.json", result.source_profile)
        _write_json(target / "delivery_preset_snapshot.json", result.delivery_preset)
        _write_json(target / "planning_profile_snapshot.json", result.planning_profile)
        _write_json(target / "session_pack_plan.json", result.session_pack_plan)
        _write_json(session_dir / "session_plan.json", result.session_plan)
        _write_json(session_dir / "macro_state_plan.json", result.macro_state_plan)
        _write_json(session_dir / "packet_plan.json", result.packet_plan)
        _write_json(
            session_dir / "pulse_pattern_plan.json",
            result.packet_plan["pulse_pattern_plan"],
        )
        _write_json(
            session_dir / "channel_unit_plan.json",
            result.packet_plan["channel_unit_plan"],
        )
        _write_json(session_dir / "event_plan.json", result.event_plan)
        _write_json(session_dir / "validation_report.json", result.validation_report)
        events = result.event_plan["events"]
        with (session_dir / "events.csv").open("w", newline="", encoding="utf-8") as handle:
            fields = [
                "event_id", "session_id", "packet_id", "unit_id", "pulse_role",
                "onset_sample", "duration_samples", "end_sample_exclusive",
                "logical_channel", "channel_role", "motif_id", "motif_hash",
                "motif_source_order", "identity_mode", "relative_event_gain", "gain_source",
            ]
            writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
            writer.writeheader()
            for event in events:
                writer.writerow({key: event[key] for key in fields})
        diagnostic_manifest = generate_diagnostics(result, diagnostics_dir)
        hashes = PlanningService.core_hashes(result)
        manifest = {
            "schema_version": "wge.run_manifest.v1",
            "run_id": result.run_request["request_id"],
            "core_hashes": hashes,
            "diagnostic_manifest_hash": diagnostic_manifest["content_hash"],
            "analysis_report_only": True,
            "audio_directory_created": False,
            "headroom_status": "not_certified_without_waveform_render_and_overlap_sum",
            "content_hash": "",
        }
        manifest["content_hash"] = content_hash(manifest)
        _write_json(target / "run_manifest.json", manifest)

    def list_runs(self) -> list[str]:
        values = []
        if (self.root / "latest").is_dir():
            values.append("latest")
        saved = self.root / "saved"
        if saved.is_dir():
            values.extend(f"saved/{item.name}" for item in sorted(saved.iterdir()) if item.is_dir())
        return values

    def resolve(self, value: str) -> Path:
        if value == "latest":
            target = self.root / "latest"
        elif value.startswith("saved/"):
            target = self.root / "saved" / _safe_id(value.split("/", 1)[1])
        else:
            raise ValidationFailure("Unknown run reference")
        if not target.is_dir():
            raise ValidationFailure("Run does not exist")
        return target

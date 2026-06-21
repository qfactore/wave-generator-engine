import json
import subprocess
from dataclasses import asdict
from pathlib import Path
from typing import Any

from wave_generator_engine import __version__
from wave_generator_engine.config import AUTHORITY_ARTIFACT_SCHEMAS, ENGINE_ROOT
from wave_generator_engine.errors import WGEError
from wave_generator_engine.gates.registry import GateRegistry
from wave_generator_engine.gates.naming_hygiene import scan_engine_owned_files
from .authority_tiers import validate_authority_tiers
from .closure_policies import ClosurePolicies
from .frozen_authority import validate_frozen_authority
from .loader import parse_required_json
from .manifest import load_handoff
from .schema_validation import compile_schemas, validate_authority_artifacts


def _git_status() -> str:
    result = subprocess.run(
        ["git", "status", "--short", "--branch"],
        cwd=ENGINE_ROOT, text=True, capture_output=True, check=False,
    )
    return result.stdout.strip() or "clean"


def validate_interchange(root: Path, forbidden_terms: tuple[str, ...] = ()) -> dict[str, Any]:
    handoff = load_handoff(root)
    parsed = parse_required_json(root, handoff.required_paths)
    schemas = compile_schemas(root, handoff.schema_paths)
    validated = validate_authority_artifacts(root, schemas, parsed)
    artifacts = [parsed[path] for path in AUTHORITY_ARTIFACT_SCHEMAS]
    decisions = parsed["manifests/decision_registry.json"]
    validate_authority_tiers(
        artifacts, decisions, parsed["manifests/source_artifact_manifest.json"]
    )
    ClosurePolicies(*artifacts).validate()
    frozen = validate_frozen_authority(root)
    registry = GateRegistry.from_authority(handoff.data, decisions, artifacts)
    naming = scan_engine_owned_files(ENGINE_ROOT, forbidden_terms)
    canonical = parsed["manifests/canonical_interchange_manifest.json"]
    upstream_ready = parsed["reports/wg_i8_readiness_report.json"]
    return {
        "engine_version": __version__,
        "interchange_manifest_version": canonical.get("manifest_version"),
        "interchange_phase": canonical.get("generated_by_phase"),
        "interchange_readiness": upstream_ready.get("readiness"),
        "required_paths_resolved": len(handoff.required_paths),
        "json_files_parsed": len(parsed),
        "schemas_discovered": len(handoff.schema_paths),
        "schemas_compiled": len(schemas),
        "authority_artifacts_validated": len(validated),
        "frozen_authority": asdict(frozen),
        "authority_tiers_valid": True,
        "gate_coverage": {"valid": True, "count": len(registry)},
        "naming_hygiene": {"valid": naming.clean, "files_scanned": naming.files_scanned},
        "profile_scaffold": {"valid": (ENGINE_ROOT / "profiles/registry.json").is_file()},
        "git_status": _git_status(),
        "warnings": list(handoff.warnings),
        "renderer_exists": False,
        "scheduler_exists": False,
        "transform_executor_exists": False,
        "audio_generated": False,
        "playback_json_generated": False,
        "interchange_modified": False,
        "wge1_started": False,
        "final_status": "WGE0_ENGINE_SCAFFOLD_READY",
    }


def write_reports(report_dir: Path, report: dict[str, Any]) -> None:
    report_dir.mkdir(parents=True, exist_ok=True)
    (report_dir / "wge0_readiness_report.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    lines = [
        "# WGE-0 Readiness Report", "",
        f"Status: {report['final_status']}", "",
        f"- Engine version: {report['engine_version']}",
        f"- Interchange manifest version: {report['interchange_manifest_version']}",
        f"- Interchange phase: {report['interchange_phase']}",
        f"- Required paths resolved: {report['required_paths_resolved']}",
        f"- JSON files parsed: {report['json_files_parsed']}",
        f"- Schemas compiled: {report['schemas_compiled']}",
        f"- WG-I8 artifacts validated: {report['authority_artifacts_validated']}",
        f"- Frozen archive hash: {'matched' if report['frozen_authority']['hash_matches'] else 'failed'}",
        f"- Frozen identities: {report['frozen_authority']['identity_count']}",
        f"- Authority tiers: {'valid' if report['authority_tiers_valid'] else 'failed'}",
        f"- Gate coverage: {report['gate_coverage']['count']} gates",
        f"- Naming hygiene: {'valid' if report['naming_hygiene']['valid'] else 'failed'}",
        f"- Profile scaffold: {'valid' if report['profile_scaffold']['valid'] else 'failed'}",
        f"- Git status: {report['git_status']}",
        "",
        "No renderer, scheduler, transform executor, audio output, or playback payload exists.",
        "The Interchange was not modified. WGE-1 has not started.",
    ]
    if report["warnings"]:
        lines.extend(["", "Warnings:", *[f"- {item}" for item in report["warnings"]]])
    (report_dir / "WGE0_READINESS_REPORT.md").write_text(
        "\n".join(lines) + "\n", encoding="utf-8"
    )


def write_failure_report(report_dir: Path, error: WGEError) -> None:
    write_reports(report_dir, {
        "engine_version": __version__,
        "interchange_manifest_version": None,
        "interchange_phase": None,
        "interchange_readiness": None,
        "required_paths_resolved": 0,
        "json_files_parsed": 0,
        "schemas_discovered": 0,
        "schemas_compiled": 0,
        "authority_artifacts_validated": 0,
        "frozen_authority": {"hash_matches": False, "identity_count": 0},
        "authority_tiers_valid": False,
        "gate_coverage": {"valid": False, "count": 0},
        "naming_hygiene": {"valid": False, "files_scanned": 0},
        "profile_scaffold": {"valid": False},
        "git_status": _git_status(),
        "warnings": [str(error)],
        "renderer_exists": False,
        "scheduler_exists": False,
        "transform_executor_exists": False,
        "audio_generated": False,
        "playback_json_generated": False,
        "interchange_modified": False,
        "wge1_started": False,
        "final_status": "REVISE_WGE0_ENGINE_SCAFFOLD",
    })

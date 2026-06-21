import argparse
import json
import os
from pathlib import Path
from typing import Any

from wave_generator_engine.config import ENGINE_ROOT, FORBIDDEN_TERMS_ENV, PROFILE_ROOT
from wave_generator_engine.errors import WGEError, ValidationFailure
from wave_generator_engine.interchange.discovery import discover_interchange
from wave_generator_engine.interchange.readiness import (
    validate_interchange, write_failure_report, write_reports,
)


def _json_flag(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--json", action="store_true", dest="json_output")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="wge")
    commands = parser.add_subparsers(dest="command", required=True)
    validate = commands.add_parser("validate-interchange")
    validate.add_argument("--interchange-dir", type=Path)
    validate.add_argument("--report-dir", type=Path, default=ENGINE_ROOT / "reports")
    validate.add_argument("--forbidden-term", action="append", default=[])

    profiles = commands.add_parser("profiles")
    profile_commands = profiles.add_subparsers(dest="profile_command", required=True)
    for name in ("list", "validate"):
        _json_flag(profile_commands.add_parser(name))
    show = profile_commands.add_parser("show")
    show.add_argument("profile_id")
    _json_flag(show)
    validate_file = profile_commands.add_parser("validate-file")
    validate_file.add_argument("path", type=Path)
    _json_flag(validate_file)
    fork = profile_commands.add_parser("fork")
    fork.add_argument("profile_id")
    fork.add_argument("--new-id", required=True)
    fork.add_argument("--display-name", required=True)
    fork.add_argument("--trust-level", default="bounded")
    fork.add_argument("--profile-dir", type=Path, default=PROFILE_ROOT)
    _json_flag(fork)

    presets = commands.add_parser("presets")
    preset_commands = presets.add_subparsers(dest="preset_command", required=True)
    _json_flag(preset_commands.add_parser("list"))
    preset_show = preset_commands.add_parser("show")
    preset_show.add_argument("preset_id")
    _json_flag(preset_show)

    levers = commands.add_parser("levers")
    lever_commands = levers.add_subparsers(dest="lever_command", required=True)
    _json_flag(lever_commands.add_parser("list"))
    lever_show = lever_commands.add_parser("show")
    lever_show.add_argument("lever_id")
    _json_flag(lever_show)

    requests = commands.add_parser("requests")
    request_commands = requests.add_subparsers(dest="request_command", required=True)
    request_validate = request_commands.add_parser("validate")
    request_validate.add_argument("path", type=Path)
    _json_flag(request_validate)

    motifs = commands.add_parser("motifs")
    motif_commands = motifs.add_subparsers(dest="motif_command", required=True)
    for name in ("validate", "list", "summarize"):
        command = motif_commands.add_parser(name)
        command.add_argument("--interchange-dir", type=Path)
        _json_flag(command)
    motif_show = motif_commands.add_parser("show")
    motif_show.add_argument("motif_id")
    motif_show.add_argument("--interchange-dir", type=Path)
    _json_flag(motif_show)
    motif_exact = motif_commands.add_parser("verify-exact")
    motif_exact.add_argument("motif_id")
    motif_exact.add_argument("--interchange-dir", type=Path)
    _json_flag(motif_exact)

    calibration = commands.add_parser("calibration")
    calibration_commands = calibration.add_subparsers(
        dest="calibration_command", required=True
    )
    for name in ("inspect", "preflight"):
        command = calibration_commands.add_parser(name)
        command.add_argument("--interchange-dir", type=Path)
        _json_flag(command)
    return parser


def _emit(payload: Any, as_json: bool) -> None:
    if as_json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    elif isinstance(payload, list):
        for item in payload:
            print(item if isinstance(item, str) else item.get("id", item))
    elif isinstance(payload, dict):
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(payload)


def _profile_command(args: argparse.Namespace) -> int:
    from wave_generator_engine.profiles.fork import fork_profile
    from wave_generator_engine.profiles.loader import load_document
    from wave_generator_engine.profiles.registry import Registry
    from wave_generator_engine.profiles.validation import validate_source_profile

    registry = Registry.load()
    if args.profile_command == "list":
        _emit([item["id"] for item in registry.entries("source_profile")], args.json_output)
    elif args.profile_command == "show":
        entry = registry.get(args.profile_id)
        if entry["kind"] != "source_profile":
            raise ValidationFailure("Requested ID is not a source profile")
        _emit(registry.load_entry(args.profile_id), args.json_output)
    elif args.profile_command == "validate":
        _emit({"valid": True, "entries": len(registry.entries())}, args.json_output)
    elif args.profile_command == "validate-file":
        document = load_document(args.path)
        validate_source_profile(document)
        _emit({"valid": True, "profile_id": document["profile_id"]}, args.json_output)
    elif args.profile_command == "fork":
        profile_path, record_path = fork_profile(
            args.profile_id, args.new_id, args.display_name, args.trust_level,
            profile_root=args.profile_dir,
        )
        _emit({
            "created": True,
            "profile": str(profile_path.relative_to(args.profile_dir)),
            "fork_record": str(record_path.relative_to(args.profile_dir)),
        }, args.json_output)
    return 0


def _preset_command(args: argparse.Namespace) -> int:
    from wave_generator_engine.profiles.registry import Registry
    registry = Registry.load()
    if args.preset_command == "list":
        _emit([item["id"] for item in registry.entries("delivery_preset")], args.json_output)
    else:
        entry = registry.get(args.preset_id)
        if entry["kind"] != "delivery_preset":
            raise ValidationFailure("Requested ID is not a delivery preset")
        _emit(registry.load_entry(args.preset_id), args.json_output)
    return 0


def _lever_command(args: argparse.Namespace) -> int:
    from wave_generator_engine.levers.registry import get_lever, load_lever_registry
    if args.lever_command == "list":
        _emit([item["lever_id"] for item in load_lever_registry()["levers"]], args.json_output)
    else:
        _emit(get_lever(args.lever_id), args.json_output)
    return 0


def _request_command(args: argparse.Namespace) -> int:
    from wave_generator_engine.profiles.loader import load_document
    from wave_generator_engine.profiles.registry import Registry
    from wave_generator_engine.requests.validation import validate_run_request
    result = validate_run_request(load_document(args.path), Registry.load())
    _emit(result, args.json_output)
    return 0


def _motif_command(args: argparse.Namespace) -> int:
    from wave_generator_engine.motifs.service import FrozenMotifService

    service = FrozenMotifService.load(args.interchange_dir)
    if args.motif_command == "validate":
        payload = service.validate()
    elif args.motif_command == "list":
        payload = service.list_metadata()
    elif args.motif_command == "show":
        payload = service.show(args.motif_id)
    elif args.motif_command == "verify-exact":
        payload = service.verify_exact(args.motif_id)
    else:
        payload = service.summarize()
    _emit(payload, args.json_output)
    return 0


def _calibration_command(args: argparse.Namespace) -> int:
    from dataclasses import asdict
    from wave_generator_engine.calibration.policy import load_calibration_policy
    from wave_generator_engine.calibration.preflight import run_calibration_preflight
    from wave_generator_engine.motifs.loader import FrozenMotifBank

    policy = load_calibration_policy(args.interchange_dir)
    if args.calibration_command == "inspect":
        payload = asdict(policy)
    else:
        bank = FrozenMotifBank.load(args.interchange_dir)
        payload = run_calibration_preflight(bank, policy)
    _emit(payload, args.json_output)
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "validate-interchange":
            env_terms = tuple(filter(None, os.environ.get(FORBIDDEN_TERMS_ENV, "").split(",")))
            terms = tuple(args.forbidden_term) + env_terms
            root = discover_interchange(ENGINE_ROOT, args.interchange_dir)
            report = validate_interchange(root, terms)
            write_reports(args.report_dir, report)
            print("WGE0_ENGINE_SCAFFOLD_READY")
            return 0
        if args.command == "profiles":
            return _profile_command(args)
        if args.command == "presets":
            return _preset_command(args)
        if args.command == "levers":
            return _lever_command(args)
        if args.command == "requests":
            return _request_command(args)
        if args.command == "motifs":
            return _motif_command(args)
        if args.command == "calibration":
            return _calibration_command(args)
    except WGEError as exc:
        if args.command == "validate-interchange":
            write_failure_report(args.report_dir, exc)
        print(json.dumps({"valid": False, "error": str(exc)}) if getattr(args, "json_output", False)
              else f"REVISE_WGE1_PROFILE_SYSTEM: {exc}")
        return 1
    return 1

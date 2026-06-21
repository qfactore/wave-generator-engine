import argparse
import os
from pathlib import Path

from wave_generator_engine.config import ENGINE_ROOT, FORBIDDEN_TERMS_ENV
from wave_generator_engine.errors import WGEError
from wave_generator_engine.interchange.discovery import discover_interchange
from wave_generator_engine.interchange.readiness import (
    validate_interchange, write_failure_report, write_reports,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="wge")
    commands = parser.add_subparsers(dest="command", required=True)
    validate = commands.add_parser("validate-interchange")
    validate.add_argument("--interchange-dir", type=Path)
    validate.add_argument("--report-dir", type=Path, default=ENGINE_ROOT / "reports")
    validate.add_argument("--forbidden-term", action="append", default=[])
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    env_terms = tuple(filter(None, os.environ.get(FORBIDDEN_TERMS_ENV, "").split(",")))
    terms = tuple(args.forbidden_term) + env_terms
    try:
        root = discover_interchange(ENGINE_ROOT, args.interchange_dir)
        report = validate_interchange(root, terms)
        write_reports(args.report_dir, report)
    except WGEError as exc:
        write_failure_report(args.report_dir, exc)
        print(f"REVISE_WGE0_ENGINE_SCAFFOLD: {exc}")
        return 1
    print("WGE0_ENGINE_SCAFFOLD_READY")
    return 0

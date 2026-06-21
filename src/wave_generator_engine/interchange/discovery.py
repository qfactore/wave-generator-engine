import os
from pathlib import Path

from wave_generator_engine.config import INTERCHANGE_ENV
from wave_generator_engine.errors import DiscoveryError

MARKERS = (
    "handoff/handoff_manifest.json",
    "manifests/canonical_interchange_manifest.json",
    "manifests/decision_registry.json",
)


def _validate_root(candidate: Path) -> Path:
    root = candidate.expanduser().resolve()
    if not root.is_dir():
        raise DiscoveryError("Interchange root is missing or is not a directory")
    missing = [item for item in MARKERS if not (root / item).is_file()]
    if missing:
        raise DiscoveryError(
            "Interchange root is incomplete: " + ", ".join(missing)
        )
    return root


def discover_interchange(
    engine_root: Path,
    explicit: Path | None = None,
    environ: dict[str, str] | None = None,
) -> Path:
    env = os.environ if environ is None else environ
    if explicit is not None:
        return _validate_root(explicit)
    if env.get(INTERCHANGE_ENV):
        configured = [item for item in env[INTERCHANGE_ENV].split(os.pathsep) if item]
        if len(configured) != 1:
            raise DiscoveryError("Interchange environment override is ambiguous")
        return _validate_root(Path(configured[0]))
    parent = engine_root.resolve().parent
    matches = [
        path for path in parent.iterdir()
        if path.name.casefold() == "wave-gen-interchange"
    ]
    if len(matches) > 1:
        raise DiscoveryError("Interchange sibling discovery is ambiguous")
    sibling = parent / "wave-gen-interchange"
    return _validate_root(sibling)

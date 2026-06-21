import copy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from wave_generator_engine.config import PROFILE_ROOT
from wave_generator_engine.domain.trust_level import TrustLevel
from wave_generator_engine.errors import ValidationFailure
from .hashing import content_hash
from .loader import load_document, write_document
from .registry import Registry
from .validation import validate_source_profile


def _assert_no_cycle(parent: dict[str, Any], new_id: str, registry: Registry) -> None:
    seen = {new_id}
    current = parent
    while current.get("parent_profile_id"):
        parent_id = current["parent_profile_id"]
        if parent_id in seen:
            raise ValidationFailure("Cyclic parent chain rejected")
        seen.add(parent_id)
        current = registry.load_entry(parent_id)


def fork_profile(
    parent_id: str,
    new_id: str,
    display_name: str,
    requested_trust_level: str = "bounded",
    profile_root: Path = PROFILE_ROOT,
    now: str | None = None,
) -> tuple[Path, Path]:
    registry = Registry.load(profile_root)
    if any(item["id"] == new_id for item in registry.entries()):
        raise ValidationFailure("New profile ID already exists")
    TrustLevel(requested_trust_level)
    parent = registry.load_entry(parent_id)
    validate_source_profile(parent)
    if parent["content_hash"] != content_hash(parent):
        raise ValidationFailure("Parent hash mismatch")
    _assert_no_cycle(parent, new_id, registry)
    destination = profile_root / "active" / new_id
    if destination.exists():
        raise ValidationFailure("Fork destination already exists")
    timestamp = now or datetime.now(timezone.utc).isoformat()
    child = copy.deepcopy(parent)
    child.update({
        "profile_id": new_id,
        "display_name": display_name,
        "profile_version": "0.1.0-draft",
        "profile_status": "draft",
        "trust_level": requested_trust_level,
        "immutable": False,
        "selectable": False,
        "implementation_phase": "WGE-2-or-later",
        "parent_profile_id": parent["profile_id"],
        "parent_content_hash": parent["content_hash"],
        "parent_profile_version": parent["profile_version"],
        "created_at": timestamp,
        "notes": ["Draft fork; no generation behavior is implemented."],
    })
    child["content_hash"] = content_hash(child)
    validate_source_profile(child)
    record = {
        "schema_version": "wge.profile_fork_record.v1",
        "record_id": f"{new_id}_fork",
        "new_profile_id": new_id,
        "parent_profile_id": parent["profile_id"],
        "parent_content_hash": parent["content_hash"],
        "parent_profile_version": parent["profile_version"],
        "forked_at": timestamp,
        "requested_trust_level": requested_trust_level,
        "changed_fields": ["profile_id", "display_name", "profile_version", "profile_status",
                           "trust_level", "immutable", "selectable", "created_at", "notes"],
        "authority_snapshot": copy.deepcopy(parent["authority_snapshot"]),
        "content_hash": "",
    }
    record["content_hash"] = content_hash(record)
    from .validation import validate_schema
    validate_schema(record, "profile_fork_record.schema.json")
    write_document(destination / "source_profile.json", child)
    write_document(destination / "fork_record.json", record)
    registry_data = copy.deepcopy(registry.data)
    registry_data["entries"].append({
        "id": new_id,
        "kind": "source_profile",
        "path": f"active/{new_id}/source_profile.json",
        "version": child["profile_version"],
        "status": "draft",
        "content_hash": child["content_hash"],
        "selectable": False,
        "executable": False,
    })
    write_document(profile_root / "registry.json", registry_data)
    return destination / "source_profile.json", destination / "fork_record.json"

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from wave_generator_engine.config import PROFILE_ROOT
from wave_generator_engine.errors import ValidationFailure
from .hashing import validate_content_hash
from .loader import load_document
from .validation import validate_source_profile


@dataclass(frozen=True)
class Registry:
    root: Path
    data: dict[str, Any]

    @classmethod
    def load(cls, root: Path = PROFILE_ROOT) -> "Registry":
        data = load_document(root / "registry.json")
        registry = cls(root, data)
        registry.validate()
        return registry

    def entries(self, kind: str | None = None) -> list[dict[str, Any]]:
        values = self.data["entries"]
        return [item for item in values if kind is None or item["kind"] == kind]

    def get(self, item_id: str) -> dict[str, Any]:
        matches = [item for item in self.entries() if item["id"] == item_id]
        if len(matches) != 1:
            raise ValidationFailure(f"Unknown or ambiguous registry ID: {item_id}")
        return matches[0]

    def load_entry(self, item_id: str) -> dict[str, Any]:
        return load_document(self.root / self.get(item_id)["path"])

    def validate(self) -> None:
        from wave_generator_engine.levers.validation import validate_lever_registry, validate_view
        from wave_generator_engine.presets.validation import validate_delivery_preset

        from wave_generator_engine.profiles.validation import validate_schema
        validate_schema(self.data, "profile_registry.schema.json")
        entries = self.data.get("entries")
        if not isinstance(entries, list):
            raise ValidationFailure("Profile registry entries are invalid")
        ids = [item.get("id") for item in entries]
        paths = [item.get("path") for item in entries]
        if len(ids) != len(set(ids)) or len(paths) != len(set(paths)):
            raise ValidationFailure("Registry IDs and paths must be unique")
        allowed_kinds = {
            "source_profile", "delivery_preset", "lever_registry",
            "lever_set", "lever_view",
        }
        by_id = {item["id"]: item for item in entries}
        for entry in entries:
            if entry["kind"] not in allowed_kinds:
                raise ValidationFailure("Registry entry kind is invalid")
            path = self.root / entry["path"]
            if not path.is_file():
                raise ValidationFailure(f"Registry path is missing: {entry['id']}")
            document = load_document(path)
            if document.get("content_hash") and document["content_hash"] != entry["content_hash"]:
                raise ValidationFailure(f"Registry content hash mismatch: {entry['id']}")
            if document.get("content_hash") and not validate_content_hash(document):
                raise ValidationFailure(f"Document content hash mismatch: {entry['id']}")
            if entry.get("executable"):
                raise ValidationFailure("WGE-1 registry entries must be non-executable")
            if entry["kind"] == "source_profile":
                validate_source_profile(document)
                if entry["status"] != document["profile_status"]:
                    raise ValidationFailure("Source-profile lifecycle status mismatch")
                if entry["selectable"] != document["selectable"]:
                    raise ValidationFailure("Source-profile selectable state mismatch")
                parent = document.get("parent_profile_id")
                if parent:
                    if parent not in by_id:
                        raise ValidationFailure("Dangling parent profile reference")
                    parent_doc = load_document(self.root / by_id[parent]["path"])
                    if document["parent_content_hash"] != parent_doc["content_hash"]:
                        raise ValidationFailure("Parent content hash mismatch")
            elif entry["kind"] == "delivery_preset":
                validate_delivery_preset(document, self)
                if entry["status"] != document["status"]:
                    raise ValidationFailure("Delivery-preset lifecycle status mismatch")
            elif entry["kind"] == "lever_registry":
                validate_lever_registry(document)
            elif entry["kind"] == "lever_set":
                lever_registry_entry = next(
                    item for item in entries if item["kind"] == "lever_registry"
                )
                lever_registry = load_document(self.root / lever_registry_entry["path"])
                from wave_generator_engine.levers.validation import validate_lever_set
                validate_lever_set(document, lever_registry, document["trust_level"])
            elif entry["kind"] == "lever_view":
                validate_view(document, self)


def validate_profile_scaffold(engine_root: Path) -> None:
    """Backward-compatible WGE-0 scaffold check, now backed by full validation."""
    root = engine_root / "profiles"
    for name in ("presets", "active", "archived", "deprecated"):
        if not (root / name).is_dir():
            raise ValueError(f"Missing profile directory: {name}")
    Registry.load(root)

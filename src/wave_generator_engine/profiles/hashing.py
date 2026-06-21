import hashlib
import json
from typing import Any

HASH_EXCLUDED_FIELDS = frozenset({"content_hash"})


def canonical_json_bytes(
    document: dict[str, Any],
    excluded_fields: frozenset[str] = HASH_EXCLUDED_FIELDS,
) -> bytes:
    payload = {key: value for key, value in document.items() if key not in excluded_fields}
    return json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def content_hash(document: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_json_bytes(document)).hexdigest()


def validate_content_hash(document: dict[str, Any]) -> bool:
    declared = document.get("content_hash")
    try:
        return isinstance(declared, str) and declared == content_hash(document)
    except (TypeError, ValueError):
        return False

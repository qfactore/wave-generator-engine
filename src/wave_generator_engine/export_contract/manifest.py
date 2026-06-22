from typing import Any

from wave_generator_engine.errors import ValidationFailure
from wave_generator_engine.profiles.hashing import content_hash


class DiagnosticExportManifestBuilder:
    """Metadata-only future manifest builder; writes no audio or files."""

    @staticmethod
    def build(
        contract: dict[str, Any], source_render_receipt_hash: str,
        source_bus_hashes: dict[str, str], files: list[dict[str, Any]],
    ) -> dict[str, Any]:
        if len(files) != 4 or len(source_bus_hashes) != 8:
            raise ValidationFailure("Diagnostic export manifest cardinality is invalid")
        document = {
            "schema_version": "wge.diagnostic_export_manifest.v1",
            "contract_id": contract["contract_id"],
            "contract_hash": contract["content_hash"],
            "source_render_receipt_hash": source_render_receipt_hash,
            "source_bus_hashes": source_bus_hashes,
            "files": files,
            "calibration_already_applied": True,
            "export_calibration_multiplier": 1.0,
            "playback_intensity_applied": False,
            "content_hash": "",
        }
        document["content_hash"] = content_hash(document)
        return document

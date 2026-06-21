from pathlib import Path
from typing import Any

from .identity import ExactIdentityAccess
from .loader import FrozenMotifBank
from .metrics import inspect_record, summarize_corpus


class FrozenMotifService:
    def __init__(self, bank: FrozenMotifBank) -> None:
        self.bank = bank
        self.exact = ExactIdentityAccess(bank)

    @classmethod
    def load(cls, interchange_dir: Path | None = None) -> "FrozenMotifService":
        return cls(FrozenMotifBank.load(interchange_dir))

    def validate(self) -> dict[str, Any]:
        return {
            "valid": True,
            "authority_classification": self.bank.authority.classification_status,
            "authority_tier": self.bank.authority.authority_tier,
            "pre_access_hash": self.bank.pre_access_hash,
            "post_access_hash": self.bank.post_access_hash,
            "motif_count": len(self.bank),
            "unique_identity_count": len(set(self.bank.ids())),
            "per_motif_hash_verification_count": len(self.bank),
            "shape_validation": "passed",
            "dtype_validation": "passed",
            "read_only_validation": all(not item.samples.flags.writeable for item in self.bank.records()),
        }

    def list_metadata(self) -> list[dict[str, Any]]:
        return [item.metadata.to_dict() for item in self.bank.records()]

    def show(self, motif_id: str) -> dict[str, Any]:
        return inspect_record(self.bank.get(motif_id))

    def verify_exact(self, motif_id: str) -> dict[str, Any]:
        _, receipt = self.exact.access(motif_id)
        return receipt.to_dict()

    def summarize(self) -> dict[str, Any]:
        return summarize_corpus(self.bank.records())

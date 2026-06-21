"""Read-only Frozen Alpha Motif Corpus access."""

from .identity import ExactIdentityAccess
from .service import FrozenMotifService

__all__ = ["ExactIdentityAccess", "FrozenMotifService"]

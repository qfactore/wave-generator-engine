from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from .delivery_preset import DeliveryPreset
from .export_target import ExportTarget
from .session_selection import SessionSelection


class ProvenanceRequirement(StrEnum):
    REQUIRED = "required"


class SessionPackPlan(Protocol):
    """Future validated pack-plan seam; no implementation exists."""


class SessionPlan(Protocol):
    """Future session-plan seam; no implementation exists."""


class RenderPlan(Protocol):
    """Future render-plan seam; no implementation exists."""


@dataclass(frozen=True)
class PlanningRequest:
    selection: SessionSelection
    delivery_preset: DeliveryPreset
    export_target: ExportTarget
    provenance: ProvenanceRequirement = ProvenanceRequirement.REQUIRED

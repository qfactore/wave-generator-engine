from typing import Any, TypedDict


class RenderAuditManifest(TypedDict):
    schema_version: str
    audit_id: str
    headroom_verdict: str
    wge4b_authorized: bool
    document_hashes: dict[str, str]
    content_hash: str


class RenderReceipt(TypedDict):
    schema_version: str
    events_planned: int
    events_rendered: int
    array_hashes: dict[str, str]
    content_hash: str


class EventRenderTrace(TypedDict):
    schema_version: str
    event_count: int
    events: list[dict[str, Any]]
    content_hash: str


class ChannelRenderMetrics(TypedDict):
    schema_version: str
    uncalibrated: list[dict[str, Any]]
    calibrated: list[dict[str, Any]]
    content_hash: str


class OverlapMetrics(TypedDict):
    schema_version: str
    per_channel: list[dict[str, Any]]
    total_overlap_additions: int
    content_hash: str


class TruePeakMethodRecord(TypedDict):
    method_id: str
    phase_count: int
    support_radius_samples: int
    content_hash: str


class HeadroomVerdict(TypedDict):
    schema_version: str
    verdict: str
    wge4b_authorized: bool
    content_hash: str

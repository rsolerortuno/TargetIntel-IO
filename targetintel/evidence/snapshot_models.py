"""Immutable, deterministic contracts for reviewed-evidence snapshots.

These objects are deliberately data-only.  They neither own a store nor
perform any scientific interpretation.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
from types import MappingProxyType
from typing import Any, Mapping

from .models import EvidenceItem, ProvenanceStep, canonical_json

SNAPSHOT_REQUEST_SCHEMA_ID = "reviewed-evidence-snapshot-request"
SNAPSHOT_REQUEST_SCHEMA_VERSION = "v1"
SNAPSHOT_ENTRY_FORMAT_VERSION = "reviewed-evidence-snapshot-entry-v1"
SNAPSHOT_FORMAT_VERSION = "reviewed-evidence-snapshot-v1"
SNAPSHOT_RESULT_FORMAT_VERSION = "reviewed-evidence-snapshot-result-v1"
SELECTION_MODES = frozenset({"explicit_ids", "field_filter"})
DOWNSTREAM_PURPOSES = frozenset({"grounded_synthesis", "scientific_review", "controlled_export", "reproducibility_check"})
EMPTY_SELECTION_POLICIES = frozenset({"reject_empty", "allow_empty"})
SNAPSHOT_STATUSES = frozenset({"created", "empty_snapshot", "invalid_request", "invalid_selector", "unknown_evidence_item", "item_limit_exceeded", "store_schema_mismatch", "store_identity_mismatch", "invalid_evidence_item", "stored_payload_mismatch", "store_changed_during_snapshot", "store_read_failed", "snapshot_verification_failed"})
# This list intentionally contains only scalar fields in the public EvidenceItem contract.
FILTERABLE_FIELDS = frozenset({"target_symbol", "disease_name", "disease_id", "evidence_type", "species", "model_system", "evidence_direction", "validation_status", "source", "source_id"})


def _digest(value: Mapping[str, Any]) -> str:
    return sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _utc(value: datetime | None, name: str) -> datetime | None:
    if value is None:
        return None
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware UTC")
    return value.astimezone(timezone.utc)


def _freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({str(key): _freeze(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item) for item in value)
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    raise ValueError("snapshot values must be JSON-safe")


def _plain(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_plain(item) for item in value]
    return value


def _nonempty(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return value


def _reject_unsafe(value: Any) -> None:
    """Reject secrets and hidden-reasoning fields recursively, fail closed."""
    if isinstance(value, Mapping):
        for key, item in value.items():
            key_text = str(key).casefold().replace("-", "_")
            if any(token in key_text for token in ("secret", "password", "credential", "api_key", "token", "thinking", "reasoning", "chain_of_thought")):
                raise ValueError("unsafe snapshot request field")
            _reject_unsafe(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            _reject_unsafe(item)


def _selector(mode: str, selector: Any) -> Mapping[str, Any]:
    _reject_unsafe(selector)
    if mode == "explicit_ids":
        if not isinstance(selector, Mapping) or set(selector) != {"evidence_item_ids"}:
            raise ValueError("explicit_ids selector must contain only evidence_item_ids")
        ids = selector["evidence_item_ids"]
        if not isinstance(ids, (list, tuple)):
            raise ValueError("evidence_item_ids must be a list")
        if any(not isinstance(item, str) or not item.strip() for item in ids):
            raise ValueError("evidence_item_ids must contain non-blank strings")
        if len(set(ids)) != len(ids):
            raise ValueError("evidence_item_ids must not contain duplicates")
        return MappingProxyType({"evidence_item_ids": tuple(sorted(ids))})
    if mode == "field_filter":
        if not isinstance(selector, Mapping) or not selector:
            raise ValueError("field_filter selector must be a non-empty mapping")
        if set(selector) - FILTERABLE_FIELDS:
            raise ValueError("unknown field_filter field")
        normalized: dict[str, Any] = {}
        for field, value in selector.items():
            if isinstance(value, str) and value:
                normalized[field] = value
            elif isinstance(value, (list, tuple)) and value and all(isinstance(item, str) and item for item in value):
                if len(set(value)) != len(value):
                    raise ValueError("field_filter membership values must not contain duplicates")
                normalized[field] = tuple(sorted(value))
            else:
                raise ValueError("field_filter values must be exact non-empty strings or controlled string lists")
        return MappingProxyType({key: normalized[key] for key in sorted(normalized)})
    raise ValueError("unknown selection mode")


@dataclass(frozen=True)
class EvidenceSnapshotRequest:
    request_schema_id: str
    request_schema_version: str
    snapshot_request_id: str
    logical_store_id: str
    expected_store_schema_version: str | None
    selection_mode: str
    selector: Mapping[str, Any]
    requesting_actor_id: str
    downstream_purpose: str
    empty_selection_policy: str
    maximum_accepted_item_count: int | None = None
    requested_at: datetime | None = None

    def __post_init__(self) -> None:
        if self.request_schema_id != SNAPSHOT_REQUEST_SCHEMA_ID or self.request_schema_version != SNAPSHOT_REQUEST_SCHEMA_VERSION:
            raise ValueError("unknown snapshot request schema")
        for name in ("snapshot_request_id", "logical_store_id", "requesting_actor_id"):
            _nonempty(getattr(self, name), name)
        if self.expected_store_schema_version is not None:
            _nonempty(self.expected_store_schema_version, "expected_store_schema_version")
        if self.selection_mode not in SELECTION_MODES or self.downstream_purpose not in DOWNSTREAM_PURPOSES or self.empty_selection_policy not in EMPTY_SELECTION_POLICIES:
            raise ValueError("unknown snapshot request vocabulary")
        normalized = _selector(self.selection_mode, self.selector)
        if self.selection_mode == "field_filter" and (not isinstance(self.maximum_accepted_item_count, int) or isinstance(self.maximum_accepted_item_count, bool) or self.maximum_accepted_item_count <= 0):
            raise ValueError("field_filter requires a positive maximum_accepted_item_count")
        if self.selection_mode == "explicit_ids" and self.maximum_accepted_item_count is not None and (not isinstance(self.maximum_accepted_item_count, int) or isinstance(self.maximum_accepted_item_count, bool) or self.maximum_accepted_item_count <= 0):
            raise ValueError("maximum_accepted_item_count must be positive when supplied")
        if self.selection_mode == "explicit_ids" and not normalized["evidence_item_ids"]:
            if self.empty_selection_policy != "allow_empty":
                raise ValueError("explicit_ids requires at least one evidence_item_id")
        object.__setattr__(self, "selector", normalized)
        object.__setattr__(self, "requested_at", _utc(self.requested_at, "requested_at"))
        if self.snapshot_request_id != _digest(self.identity_payload()):
            raise ValueError("snapshot request identity does not match payload")

    def identity_payload(self) -> dict[str, Any]:
        return {"request_schema_id": self.request_schema_id, "request_schema_version": self.request_schema_version, "logical_store_id": self.logical_store_id, "expected_store_schema_version": self.expected_store_schema_version, "selection_mode": self.selection_mode, "selector": _plain(self.selector), "requesting_actor_id": self.requesting_actor_id, "downstream_purpose": self.downstream_purpose, "empty_selection_policy": self.empty_selection_policy, "maximum_accepted_item_count": self.maximum_accepted_item_count}

    def to_dict(self) -> dict[str, Any]:
        value = self.identity_payload() | {"snapshot_request_id": self.snapshot_request_id}
        if self.requested_at is not None:
            value["requested_at"] = self.requested_at.isoformat(timespec="microseconds").replace("+00:00", "Z")
        return value

    def canonical_json(self) -> str: return canonical_json(self.to_dict())

    @classmethod
    def create(cls, *, logical_store_id: str, selection_mode: str, selector: Mapping[str, Any], requesting_actor_id: str, downstream_purpose: str, empty_selection_policy: str, expected_store_schema_version: str | None = None, maximum_accepted_item_count: int | None = None, requested_at: datetime | None = None) -> "EvidenceSnapshotRequest":
        provisional = {"request_schema_id": SNAPSHOT_REQUEST_SCHEMA_ID, "request_schema_version": SNAPSHOT_REQUEST_SCHEMA_VERSION, "logical_store_id": logical_store_id, "expected_store_schema_version": expected_store_schema_version, "selection_mode": selection_mode, "selector": selector, "requesting_actor_id": requesting_actor_id, "downstream_purpose": downstream_purpose, "empty_selection_policy": empty_selection_policy, "maximum_accepted_item_count": maximum_accepted_item_count}
        normalized = _selector(selection_mode, selector)
        identity = provisional | {"selector": _plain(normalized)}
        provisional["selector"] = normalized
        return cls(**provisional, snapshot_request_id=_digest(identity), requested_at=requested_at)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "EvidenceSnapshotRequest":
        allowed = {"request_schema_id", "request_schema_version", "snapshot_request_id", "logical_store_id", "expected_store_schema_version", "selection_mode", "selector", "requesting_actor_id", "downstream_purpose", "empty_selection_policy", "maximum_accepted_item_count", "requested_at"}
        if not isinstance(data, Mapping) or set(data) - allowed or (allowed - {"expected_store_schema_version", "maximum_accepted_item_count", "requested_at"}) - set(data):
            raise ValueError("invalid snapshot request fields")
        _reject_unsafe(data)
        values = dict(data)
        # The field is optional in the wire contract even though the dataclass
        # keeps the public constructor explicit.  Normalize its absence here
        # so malformed input consistently fails through contract validation,
        # rather than leaking a Python constructor TypeError.
        values.setdefault("expected_store_schema_version", None)
        if isinstance(values.get("requested_at"), str): values["requested_at"] = datetime.fromisoformat(values["requested_at"].replace("Z", "+00:00"))
        return cls(**values)


def _frozen_item(item: EvidenceItem) -> EvidenceItem:
    values = {name: getattr(item, name) for name in item.__dataclass_fields__}
    values["provenance_history"] = tuple(ProvenanceStep(step_type=step.step_type, recorded_at=step.recorded_at, details=_freeze(step.details), is_operational=step.is_operational) for step in item.provenance_history)
    return EvidenceItem(**values)


@dataclass(frozen=True)
class EvidenceSnapshotEntry:
    entry_format_version: str
    snapshot_entry_id: str
    evidence_item_id: str
    canonical_payload_hash: str
    evidence_item: EvidenceItem
    provenance_references: Mapping[str, Any]
    logical_store_id: str
    store_schema_version: str | None

    def __post_init__(self) -> None:
        if self.entry_format_version != SNAPSHOT_ENTRY_FORMAT_VERSION or not isinstance(self.evidence_item, EvidenceItem): raise ValueError("invalid snapshot entry")
        if self.evidence_item_id != self.evidence_item.evidence_id: raise ValueError("entry evidence item identity mismatch")
        if self.canonical_payload_hash != sha256(self.evidence_item.canonical_json().encode("utf-8")).hexdigest(): raise ValueError("entry payload hash mismatch")
        object.__setattr__(self, "evidence_item", _frozen_item(self.evidence_item))
        object.__setattr__(self, "provenance_references", _freeze(self.provenance_references))
        if self.snapshot_entry_id != _digest(self.identity_payload()): raise ValueError("snapshot entry identity does not match payload")

    def identity_payload(self) -> dict[str, Any]: return {"entry_format_version": self.entry_format_version, "evidence_item_id": self.evidence_item_id, "canonical_payload_hash": self.canonical_payload_hash, "provenance_references": _plain(self.provenance_references), "logical_store_id": self.logical_store_id, "store_schema_version": self.store_schema_version}
    def to_dict(self) -> dict[str, Any]: return self.identity_payload() | {"snapshot_entry_id": self.snapshot_entry_id, "evidence_item": self.evidence_item.to_dict()}
    def canonical_json(self) -> str: return canonical_json(self.to_dict())


@dataclass(frozen=True)
class ReviewedEvidenceSnapshot:
    snapshot_format_version: str; snapshot_id: str; snapshot_request_id: str; logical_store_id: str; store_schema_version: str | None; selection_mode: str; selector: Mapping[str, Any]; downstream_purpose: str; entries: tuple[EvidenceSnapshotEntry, ...]; selected_item_count: int; ordered_evidence_item_ids: tuple[str, ...]; ordered_canonical_payload_hashes: tuple[str, ...]; manifest_hash: str; snapshot_validation_state: str; research_only: bool = True; non_clinical_use: bool = True; store_mutation_occurred: bool = False; created_at: datetime | None = None
    def __post_init__(self) -> None:
        object.__setattr__(self, "entries", tuple(self.entries)); object.__setattr__(self, "selector", _freeze(self.selector)); object.__setattr__(self, "created_at", _utc(self.created_at, "created_at"))
        ids = tuple(entry.evidence_item_id for entry in self.entries)
        hashes = tuple(entry.canonical_payload_hash for entry in self.entries)
        if ids != tuple(sorted(ids)) or len(set(ids)) != len(ids) or self.ordered_evidence_item_ids != ids or self.ordered_canonical_payload_hashes != hashes or self.selected_item_count != len(ids): raise ValueError("invalid snapshot manifest ordering")
        if self.manifest_hash != _digest({"entries": [{"evidence_item_id": item_id, "canonical_payload_hash": digest} for item_id, digest in zip(ids, hashes)]}): raise ValueError("snapshot manifest hash mismatch")
        if not self.research_only or not self.non_clinical_use or self.store_mutation_occurred: raise ValueError("snapshot boundary flags are invalid")
        if self.snapshot_id != _digest(self.identity_payload()): raise ValueError("snapshot identity does not match payload")
    def identity_payload(self) -> dict[str, Any]: return {"snapshot_format_version": self.snapshot_format_version, "snapshot_request_id": self.snapshot_request_id, "logical_store_id": self.logical_store_id, "store_schema_version": self.store_schema_version, "selection_mode": self.selection_mode, "selector": _plain(self.selector), "downstream_purpose": self.downstream_purpose, "entry_ids": [entry.snapshot_entry_id for entry in self.entries], "manifest_hash": self.manifest_hash, "selected_item_count": self.selected_item_count, "research_only": self.research_only, "non_clinical_use": self.non_clinical_use}
    def to_dict(self) -> dict[str, Any]:
        value = self.identity_payload() | {"snapshot_id": self.snapshot_id, "entries": [entry.to_dict() for entry in self.entries], "ordered_evidence_item_ids": list(self.ordered_evidence_item_ids), "ordered_canonical_payload_hashes": list(self.ordered_canonical_payload_hashes), "snapshot_validation_state": self.snapshot_validation_state, "store_mutation_occurred": self.store_mutation_occurred}
        if self.created_at: value["created_at"] = self.created_at.isoformat(timespec="microseconds").replace("+00:00", "Z")
        return value
    def canonical_json(self) -> str: return canonical_json(self.to_dict())


@dataclass(frozen=True)
class EvidenceSnapshotResult:
    result_format_version: str; snapshot_result_id: str; status: str; snapshot_request_id: str | None; logical_store_id: str | None; snapshot_id: str | None; snapshot: ReviewedEvidenceSnapshot | None; codes: tuple[str, ...] = (); store_write_occurred: bool = False; completed_at: datetime | None = None
    def __post_init__(self) -> None:
        if self.result_format_version != SNAPSHOT_RESULT_FORMAT_VERSION or self.status not in SNAPSHOT_STATUSES: raise ValueError("invalid snapshot result")
        object.__setattr__(self, "codes", tuple(sorted(set(self.codes)))); object.__setattr__(self, "completed_at", _utc(self.completed_at, "completed_at"))
        success = self.status in {"created", "empty_snapshot"}
        if success != (self.snapshot is not None) or (self.snapshot is not None and self.snapshot_id != self.snapshot.snapshot_id) or self.store_write_occurred: raise ValueError("inconsistent snapshot result")
        if self.snapshot_result_id != _digest(self.identity_payload()): raise ValueError("snapshot result identity does not match payload")
    def identity_payload(self) -> dict[str, Any]: return {"result_format_version": self.result_format_version, "status": self.status, "snapshot_request_id": self.snapshot_request_id, "logical_store_id": self.logical_store_id, "snapshot_id": self.snapshot_id, "codes": list(self.codes), "store_write_occurred": self.store_write_occurred}
    def to_dict(self) -> dict[str, Any]:
        value = self.identity_payload() | {"snapshot_result_id": self.snapshot_result_id, "snapshot": None if self.snapshot is None else self.snapshot.to_dict()}
        if self.completed_at: value["completed_at"] = self.completed_at.isoformat(timespec="microseconds").replace("+00:00", "Z")
        return value
    def canonical_json(self) -> str: return canonical_json(self.to_dict())


def make_snapshot_result(**values: Any) -> EvidenceSnapshotResult:
    values.setdefault("result_format_version", SNAPSHOT_RESULT_FORMAT_VERSION); values.setdefault("codes", ()); values.setdefault("store_write_occurred", False)
    values["codes"] = tuple(sorted(set(values["codes"])))
    payload = {key: values.get(key) for key in ("result_format_version", "status", "snapshot_request_id", "logical_store_id", "snapshot_id", "store_write_occurred")}; payload["codes"] = list(values["codes"])
    return EvidenceSnapshotResult(snapshot_result_id=_digest(payload), **values)

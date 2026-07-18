"""Pure read-only construction of immutable reviewed-evidence snapshots."""
from __future__ import annotations

from hashlib import sha256
from typing import Any

from .models import EvidenceItem, canonical_json
from .snapshot_models import (EvidenceSnapshotEntry, EvidenceSnapshotRequest,
    ReviewedEvidenceSnapshot, SNAPSHOT_ENTRY_FORMAT_VERSION, SNAPSHOT_FORMAT_VERSION,
    make_snapshot_result)
from .store import SCHEMA_VERSION
from .validation import SemanticValidationContext, ValidationError, require_finalizable


def _hash(item: EvidenceItem) -> str:
    return sha256(item.canonical_json().encode("utf-8")).hexdigest()


def _references(item: EvidenceItem) -> dict[str, Any]:
    """Stable identifiers only; source text and operational provenance stay out."""
    return {"source": item.source, "source_id": item.source_id,
            "publication_id": item.publication_id, "source_dataset_id": item.source_dataset_id,
            "patient_cohort_id": item.patient_cohort_id, "experiment_id": item.experiment_id,
            "derived_from": tuple(sorted(item.derived_from))}


def _result(request: EvidenceSnapshotRequest | None, status: str, code: str, *, store_id: str | None = None):
    return make_snapshot_result(status=status, snapshot_request_id=None if request is None else request.snapshot_request_id,
                                logical_store_id=store_id if store_id is not None else (None if request is None else request.logical_store_id),
                                snapshot_id=None, snapshot=None, codes=(code,))


def create_reviewed_evidence_snapshot(request: EvidenceSnapshotRequest, store: Any):
    """Read persisted items and return a deterministic immutable snapshot result.

    The existing store has no transactional read-manifest API.  This service
    therefore compares the selected records before and after validation; it
    detects changes observable through its public read API but does not claim
    database-wide snapshot isolation.
    """
    if not isinstance(request, EvidenceSnapshotRequest):
        return _result(None, "invalid_request", "invalid_snapshot_request")
    store_id = getattr(store, "logical_store_id", None)
    if store_id != request.logical_store_id:
        return _result(request, "store_identity_mismatch", "store_logical_identity_mismatch", store_id=store_id)
    if request.expected_store_schema_version is not None and request.expected_store_schema_version != SCHEMA_VERSION:
        return _result(request, "store_schema_mismatch", "store_schema_version_mismatch", store_id=store_id)
    if not callable(getattr(store, "get_item", None)) or not callable(getattr(store, "list_items", None)):
        return _result(request, "store_read_failed", "store_read_api_unavailable", store_id=store_id)
    try:
        all_items = store.list_items()
        available = {item.evidence_id: item for item in all_items}
        if len(available) != len(all_items):
            return _result(request, "snapshot_verification_failed", "duplicate_evidence_item_id", store_id=store_id)
        if request.selection_mode == "explicit_ids":
            requested_ids = request.selector["evidence_item_ids"]
            missing = [item_id for item_id in requested_ids if item_id not in available]
            if missing:
                return _result(request, "unknown_evidence_item", "unknown_evidence_item", store_id=store_id)
            selected = []
            for item_id in requested_ids:
                item = store.get_item(item_id)
                if item is None:
                    return _result(request, "unknown_evidence_item", "unknown_evidence_item", store_id=store_id)
                selected.append(item)
        else:
            def matches(item: EvidenceItem) -> bool:
                for field, expected in request.selector.items():
                    actual = getattr(item, field)
                    if isinstance(expected, tuple):
                        if actual not in expected: return False
                    elif actual != expected: return False
                return True
            selected = [item for item in all_items if matches(item)]
            if len(selected) > request.maximum_accepted_item_count:
                return _result(request, "item_limit_exceeded", "maximum_accepted_item_count_exceeded", store_id=store_id)
        if (request.maximum_accepted_item_count is not None
                and len(selected) > request.maximum_accepted_item_count):
            return _result(request, "item_limit_exceeded", "maximum_accepted_item_count_exceeded", store_id=store_id)
        selected.sort(key=lambda item: item.evidence_id)
        if not selected:
            if request.empty_selection_policy == "reject_empty":
                return _result(request, "invalid_selector", "empty_selection_rejected", store_id=store_id)
            return _build_snapshot(request, store_id, (), SCHEMA_VERSION)
        # Revalidation uses a read-only context of persisted records.
        context = SemanticValidationContext(available)
        entries = []
        first_manifest = []
        for item in selected:
            try:
                require_finalizable(item, context)
            except ValidationError:
                return _result(request, "invalid_evidence_item", "evidence_item_validation_failed", store_id=store_id)
            payload_hash = _hash(item)
            if item.record_hash != payload_hash:
                return _result(request, "stored_payload_mismatch", "stored_payload_hash_mismatch", store_id=store_id)
            first_manifest.append((item.evidence_id, payload_hash))
            identity = {"entry_format_version": SNAPSHOT_ENTRY_FORMAT_VERSION, "evidence_item_id": item.evidence_id, "canonical_payload_hash": payload_hash, "provenance_references": _references(item), "logical_store_id": store_id, "store_schema_version": SCHEMA_VERSION}
            entries.append(EvidenceSnapshotEntry(snapshot_entry_id=sha256(canonical_json(identity).encode()).hexdigest(), **identity, evidence_item=item))
        # The repeat read is intentionally explicit and does not retry on change.
        second_manifest = []
        for item_id, _ in first_manifest:
            current = store.get_item(item_id)
            if current is None:
                return _result(request, "store_changed_during_snapshot", "selected_record_changed", store_id=store_id)
            second_manifest.append((item_id, _hash(current)))
        if first_manifest != second_manifest:
            return _result(request, "store_changed_during_snapshot", "selected_record_changed", store_id=store_id)
        return _build_snapshot(request, store_id, tuple(entries), SCHEMA_VERSION)
    except Exception:
        # Deliberately do not expose store exception text, paths, SQL, or tracebacks.
        return _result(request, "store_read_failed", "store_read_failed", store_id=store_id)


def _build_snapshot(request: EvidenceSnapshotRequest, store_id: str, entries: tuple[EvidenceSnapshotEntry, ...], schema_version: str):
    ids = tuple(entry.evidence_item_id for entry in entries); hashes = tuple(entry.canonical_payload_hash for entry in entries)
    manifest_hash = sha256(canonical_json({"entries": [{"evidence_item_id": item_id, "canonical_payload_hash": digest} for item_id, digest in zip(ids, hashes)]}).encode()).hexdigest()
    identity = {"snapshot_format_version": SNAPSHOT_FORMAT_VERSION, "snapshot_request_id": request.snapshot_request_id, "logical_store_id": store_id, "store_schema_version": schema_version, "selection_mode": request.selection_mode, "selector": dict(request.selector), "downstream_purpose": request.downstream_purpose, "entry_ids": [entry.snapshot_entry_id for entry in entries], "manifest_hash": manifest_hash, "selected_item_count": len(entries), "research_only": True, "non_clinical_use": True}
    snapshot_values = dict(identity)
    del snapshot_values["entry_ids"]
    snapshot = ReviewedEvidenceSnapshot(snapshot_id=sha256(canonical_json(identity).encode()).hexdigest(), **snapshot_values, entries=entries, ordered_evidence_item_ids=ids, ordered_canonical_payload_hashes=hashes, snapshot_validation_state="validated", store_mutation_occurred=False)
    return make_snapshot_result(status="empty_snapshot" if not entries else "created", snapshot_request_id=request.snapshot_request_id, logical_store_id=store_id, snapshot_id=snapshot.snapshot_id, snapshot=snapshot, codes=("stored_payload_hash_verified",), store_write_occurred=False)

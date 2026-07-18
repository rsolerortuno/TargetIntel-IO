"""Offline regression coverage for the read-only reviewed-evidence boundary."""
from __future__ import annotations

from dataclasses import replace

import pytest

from targetintel.evidence.snapshot_models import EvidenceSnapshotRequest
from targetintel.evidence.snapshots import create_reviewed_evidence_snapshot
from targetintel.evidence.store import EvidenceStore
from tests.test_evidence_models import evidence_item


def _item(evidence_id: str, **changes):
    return evidence_item(evidence_id=evidence_id, **changes).with_calculated_record_hash()


def _request(**changes):
    values = {
        "logical_store_id": "reviewed-store",
        "selection_mode": "explicit_ids",
        "selector": {"evidence_item_ids": ["ev-b", "ev-a"]},
        "requesting_actor_id": "actor-1",
        "downstream_purpose": "scientific_review",
        "empty_selection_policy": "reject_empty",
    }
    return EvidenceSnapshotRequest.create(**(values | changes))


class ReadOnlyFixtureStore:
    """Minimal public read API with write methods that must never be touched."""

    logical_store_id = "reviewed-store"

    def __init__(self, items):
        self.items = {item.evidence_id: item for item in items}
        self.write_calls = 0

    def list_items(self):
        return list(self.items.values())

    def get_item(self, evidence_id):
        return self.items.get(evidence_id)

    def insert_finalized_item(self, item):
        self.write_calls += 1
        raise AssertionError("snapshot construction must not write")


def test_real_store_selection_is_read_only_revalidated_and_canonical(tmp_path):
    path = tmp_path / "evidence.duckdb"
    with EvidenceStore(path, logical_store_id="reviewed-store") as store:
        store.insert_finalized_item(_item("ev-b", target_symbol="B2M"))
        store.insert_finalized_item(_item("ev-a", target_symbol="B2M", source_id="mock-2"))
        before_audit = store.audit_events()
        request = _request(
            selection_mode="field_filter",
            selector={"target_symbol": "B2M", "species": ["human"]},
            maximum_accepted_item_count=2,
        )
        result = create_reviewed_evidence_snapshot(request, store)
        assert result.status == "created"
        assert result.snapshot is not None
        assert result.snapshot.ordered_evidence_item_ids == ("ev-a", "ev-b")
        assert result.snapshot.manifest_hash
        assert result.store_write_occurred is False
        assert store.audit_events() == before_audit


def test_explicit_id_limit_is_enforced_without_truncation():
    store = ReadOnlyFixtureStore([_item("ev-a"), _item("ev-b", source_id="mock-2")])
    result = create_reviewed_evidence_snapshot(_request(maximum_accepted_item_count=1), store)
    assert (result.status, result.snapshot, result.codes) == (
        "item_limit_exceeded", None, ("maximum_accepted_item_count_exceeded",)
    )
    assert store.write_calls == 0


def test_unknown_and_empty_selection_fail_closed_or_require_explicit_allowance():
    store = ReadOnlyFixtureStore([])
    assert create_reviewed_evidence_snapshot(_request(selector={"evidence_item_ids": ["missing"]}), store).status == "unknown_evidence_item"
    assert create_reviewed_evidence_snapshot(_request(selector={"evidence_item_ids": []}, empty_selection_policy="allow_empty"), store).status == "empty_snapshot"
    assert store.write_calls == 0


def test_invalid_item_and_payload_hash_mismatch_prevent_snapshot():
    valid = _item("ev-a")
    invalid = replace(valid, observation="")
    invalid_store = ReadOnlyFixtureStore([invalid])
    assert create_reviewed_evidence_snapshot(_request(selector={"evidence_item_ids": ["ev-a"]}), invalid_store).status == "invalid_evidence_item"

    mismatched = replace(valid, record_hash="0" * 64)
    mismatch_store = ReadOnlyFixtureStore([mismatched])
    result = create_reviewed_evidence_snapshot(_request(selector={"evidence_item_ids": ["ev-a"]}), mismatch_store)
    assert (result.status, result.snapshot) == ("stored_payload_mismatch", None)


def test_selected_record_change_is_detected_without_retry():
    original = _item("ev-a")
    changed = _item("ev-a", observation="A changed mock observation.")

    class ChangingStore(ReadOnlyFixtureStore):
        def __init__(self):
            super().__init__([original])
            self.get_calls = 0

        def get_item(self, evidence_id):
            self.get_calls += 1
            return original if self.get_calls == 1 else changed

    store = ChangingStore()
    result = create_reviewed_evidence_snapshot(_request(selector={"evidence_item_ids": ["ev-a"]}), store)
    assert (result.status, result.snapshot, store.get_calls) == ("store_changed_during_snapshot", None, 2)
    assert store.write_calls == 0


def test_snapshot_entries_are_deeply_immutable_and_contradictions_remain_distinct():
    first = _item("ev-a", evidence_direction="supports_target")
    second = _item("ev-b", source_id="mock-2", evidence_direction="contradicts_target")
    result = create_reviewed_evidence_snapshot(_request(), ReadOnlyFixtureStore([second, first]))
    snapshot = result.snapshot
    assert result.status == "created"
    assert snapshot is not None and len(snapshot.entries) == 2
    assert [entry.evidence_item.evidence_direction for entry in snapshot.entries] == ["supports_target", "contradicts_target"]
    with pytest.raises(TypeError):
        snapshot.entries[0].evidence_item.provenance_history[0].details["changed"] = True
    with pytest.raises(TypeError):
        snapshot.entries[0].provenance_references["source"] = "changed"


def test_store_identity_schema_and_read_failures_are_sanitized():
    store = ReadOnlyFixtureStore([])
    assert create_reviewed_evidence_snapshot(_request(), object()).status == "store_identity_mismatch"
    assert create_reviewed_evidence_snapshot(_request(expected_store_schema_version="wrong"), store).status == "store_schema_mismatch"

    class FailingStore(ReadOnlyFixtureStore):
        def list_items(self):
            raise RuntimeError("postgres://user:password@host/db traceback")

    result = create_reviewed_evidence_snapshot(_request(), FailingStore([]))
    assert result.status == "store_read_failed"
    assert all(term not in result.canonical_json() for term in ("postgres", "password", "traceback"))

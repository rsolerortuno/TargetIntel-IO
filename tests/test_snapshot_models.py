from datetime import datetime, timezone

import pytest

from targetintel.evidence.snapshot_models import (
    EvidenceSnapshotRequest, SNAPSHOT_REQUEST_SCHEMA_ID,
    SNAPSHOT_REQUEST_SCHEMA_VERSION,
)


def _request(**changes):
    values = {
        "logical_store_id": "reviewed-store", "selection_mode": "explicit_ids",
        "selector": {"evidence_item_ids": ["ev-b", "ev-a"]},
        "requesting_actor_id": "actor-1", "downstream_purpose": "scientific_review",
        "empty_selection_policy": "reject_empty",
    } | changes
    return EvidenceSnapshotRequest.create(**values)


def test_request_is_canonical_immutable_and_excludes_timestamp():
    first = _request(requested_at=datetime(2026, 1, 1, tzinfo=timezone.utc))
    second = _request(selector={"evidence_item_ids": ["ev-a", "ev-b"]}, requested_at=datetime(2026, 1, 2, tzinfo=timezone.utc))
    assert (first.request_schema_id, first.request_schema_version) == (SNAPSHOT_REQUEST_SCHEMA_ID, SNAPSHOT_REQUEST_SCHEMA_VERSION)
    assert first.snapshot_request_id == second.snapshot_request_id
    with pytest.raises(TypeError):
        first.selector["x"] = "y"
    serialized = first.to_dict()
    serialized.pop("expected_store_schema_version")
    assert EvidenceSnapshotRequest.from_dict(serialized) == first


@pytest.mark.parametrize("selector", [{"evidence_item_ids": ["x", "x"]}, {"evidence_item_ids": [" "]}, {"secret": "x"}])
def test_explicit_selector_rejects_unsafe_or_ambiguous_values(selector):
    with pytest.raises(ValueError):
        _request(selector=selector)


def test_filter_requires_exact_public_field_and_limit():
    with pytest.raises(ValueError):
        _request(selection_mode="field_filter", selector={"target_symbol": "B2M"})
    request = _request(selection_mode="field_filter", selector={"target_symbol": "B2M", "species": ["human", "mouse"]}, maximum_accepted_item_count=2)
    assert request.selector["species"] == ("human", "mouse")
    with pytest.raises(ValueError):
        _request(selection_mode="field_filter", selector={"regex": ".*"}, maximum_accepted_item_count=2)


@pytest.mark.parametrize(
    "changes",
    [
        {"requesting_actor_id": ""},
        {"logical_store_id": ""},
        {"selection_mode": "latest"},
        {"downstream_purpose": "clinical_use"},
        {"selector": {"evidence_item_ids": ["x"], "hidden_reasoning": "no"}},
    ],
)
def test_request_rejects_unknown_or_unsafe_vocabulary(changes):
    with pytest.raises(ValueError):
        _request(**changes)


def test_request_from_dict_rejects_unknown_fields_without_constructor_error():
    data = _request().to_dict() | {"sql": "SELECT * FROM evidence_items"}
    with pytest.raises(ValueError):
        EvidenceSnapshotRequest.from_dict(data)

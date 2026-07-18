from dataclasses import replace
from datetime import datetime, timezone

import pytest

from targetintel.evidence.persistence_models import (
    PERSISTENCE_RECEIPT_FORMAT_VERSION,
    PERSISTENCE_REQUEST_FORMAT_VERSION,
    EvidencePersistenceRequest,
    make_receipt,
)
from tests.test_evidence_promotion import _mapping
from tests.test_grounded_extraction import _SUCCESS, _request as source_request, _response
from targetintel.llm import audit_grounded_claims, extract_grounded_candidates
from targetintel.llm.evidence_promotion import EvidencePromotionRequest, promote_candidate_to_evidence
from targetintel.llm.human_review import build_human_review_packet, create_human_review_decision


def _promoted():
    source = source_request()
    extraction = extract_grounded_candidates(source, _response(_SUCCESS))
    audit = audit_grounded_claims(extraction, "doc-1", source.source_text)
    packet = build_human_review_packet(extraction, audit)
    candidate, card, mapping = extraction.accepted_candidates[0], audit.cards[0], _mapping()
    decision = create_human_review_decision(
        packet_id=packet.packet_id, candidate_id=candidate.candidate_id, card_id=card.card_id,
        audit_result_id=audit.audit_result_id, reviewer_id="reviewer-001", decision="approve",
        decision_justification="Explicit approval.", evidence_mapping=mapping,
        reviewed_at=datetime(2026, 1, 2, tzinfo=timezone.utc),
    )
    return promote_candidate_to_evidence(EvidencePromotionRequest(
        source.source_text, "doc-1", extraction, audit, packet, decision, candidate.candidate_id, mapping,
    ))


def _request(**changes):
    values = {
        "promotion_result": _promoted(), "persistence_actor_id": "operator-001",
        "logical_store_id": "reviewed-local",
    } | changes
    return EvidencePersistenceRequest.create(**values)


def test_request_schema_identity_serialization_and_operational_metadata_are_deterministic():
    first = _request(requested_at=datetime(2024, 1, 1, tzinfo=timezone.utc))
    second = _request(requested_at=datetime(2026, 1, 1, tzinfo=timezone.utc))
    assert first.request_format_version == PERSISTENCE_REQUEST_FORMAT_VERSION
    assert first.persistence_request_id == second.persistence_request_id
    assert first.canonical_json() != second.canonical_json()
    assert "path" not in first.identity_payload()
    assert "requested_at" not in first.identity_payload()
    assert first.to_dict() == first.to_dict()
    with pytest.raises(Exception):
        first.logical_store_id = "other"


@pytest.mark.parametrize("field, value", [
    ("persistence_actor_id", ""), ("persistence_actor_id", None),
    ("logical_store_id", ""), ("logical_store_id", None),
])
def test_request_requires_explicit_nonempty_actor_and_logical_store(field, value):
    kwargs = {field: value}
    with pytest.raises(ValueError):
        _request(**kwargs)


@pytest.mark.parametrize("addition", [
    {"unknown": True}, {"api_key": "secret"}, {"reasoning": "hidden"},
])
def test_request_parser_rejects_unknown_secret_and_hidden_reasoning_fields(addition):
    request = _request()
    # from_dict intentionally receives the live immutable promotion contract;
    # Issue 306 owns promotion-result deserialization.
    payload = request.to_dict() | {"promotion_result": request.promotion_result} | addition
    with pytest.raises(ValueError):
        EvidencePersistenceRequest.from_dict(payload)


def test_request_from_dict_accepts_complete_live_promotion_contract_payload():
    request = _request()
    payload = request.to_dict() | {"promotion_result": request.promotion_result}
    assert EvidencePersistenceRequest.from_dict(payload) == request


def test_request_from_dict_parses_operational_timestamp_and_rejects_incomplete_payloads():
    request = _request(requested_at=datetime(2026, 1, 2, tzinfo=timezone.utc))
    payload = request.to_dict() | {"promotion_result": request.promotion_result}
    assert EvidencePersistenceRequest.from_dict(payload) == request
    with pytest.raises(ValueError):
        EvidencePersistenceRequest.from_dict({"promotion_result": request.promotion_result})
    with pytest.raises(ValueError):
        EvidencePersistenceRequest.from_dict(payload | {"requested_at": "not-a-timestamp"})


def test_receipt_is_immutable_deterministic_and_excludes_operational_time_and_paths():
    values = dict(
        persistence_request_id="request", idempotency_key="key", status="persisted",
        logical_store_id="reviewed-local", store_schema_version="v1", evidence_item_id="evidence",
        promotion_result_id="promotion", review_decision_id="review", packet_id="packet",
        audit_result_id="audit", card_id="card", candidate_id="candidate",
        persistence_actor_id="operator-001", canonical_stored_payload_hash="hash",
        new_write=True, persisted=True, codes=("b", "a"),
    )
    first = make_receipt(**values, persisted_at=datetime(2024, 1, 1, tzinfo=timezone.utc))
    second = make_receipt(**values, persisted_at=datetime(2026, 1, 1, tzinfo=timezone.utc))
    assert first.receipt_format_version == PERSISTENCE_RECEIPT_FORMAT_VERSION
    assert first.persistence_receipt_id == second.persistence_receipt_id
    assert first.codes == ("a", "b")
    assert "persisted_at" not in first.identity_payload()
    assert "path" not in first.identity_payload()
    with pytest.raises(Exception):
        first.status = "content_conflict"

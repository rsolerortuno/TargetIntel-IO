from dataclasses import replace
from datetime import datetime, timezone
from hashlib import sha256

import pytest

from targetintel.evidence.persistence_models import EvidencePersistenceRequest
from targetintel.evidence.reviewed_persistence import persist_promoted_evidence
from targetintel.evidence.store import EvidenceStore, StorageIntegrityError
from targetintel.llm import audit_grounded_claims, extract_grounded_candidates
from targetintel.llm.contracts import canonical_json
from targetintel.llm.evidence_promotion import EvidencePromotionRequest, EvidencePromotionResult, promote_candidate_to_evidence
from targetintel.llm.human_review import build_human_review_packet, create_human_review_decision
from tests.test_evidence_promotion import _mapping
from tests.test_grounded_extraction import _SUCCESS, _request as source_request, _response


def _digest(value):
    return sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _promotion(status="promoted", *, persisted=False):
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
    result = promote_candidate_to_evidence(EvidencePromotionRequest(
        source.source_text, "doc-1", extraction, audit, packet, decision, candidate.candidate_id, mapping,
    ))
    if status == "promoted" and not persisted:
        return result
    proto = replace(result, status=status, evidence_item=result.evidence_item if status == "promoted" else None,
                    evidence_item_id=result.evidence_item_id if status == "promoted" else None, persisted=persisted,
                    promotion_result_id="")
    return replace(proto, promotion_result_id=_digest(proto.identity_payload()))


def _request(result=None, **changes):
    result = _promotion() if result is None else result
    if result.evidence_item_id is None:
        payload = {
            "request_format_version": "reviewed-evidence-persistence-request-v1",
            "promotion_result_id": result.promotion_result_id,
            "evidence_item_id": "unavailable-evidence-item",
            "review_decision_id": result.review_decision_id or "unavailable-review-decision",
            "audit_result_id": result.audit_result_id or "unavailable-audit-result",
            "candidate_id": result.candidate_id or "unavailable-candidate",
            "persistence_actor_id": "operator-001",
            "logical_store_id": "test-store",
            "expected_store_schema_version": None,
        } | changes
        return EvidencePersistenceRequest(
            **payload, promotion_result=result, persistence_request_id=_digest(payload),
        )
    values = {"promotion_result": result, "persistence_actor_id": "operator-001", "logical_store_id": "test-store"} | changes
    return EvidencePersistenceRequest.create(**values)


def _mismatched_request(request, field):
    payload = request.identity_payload() | {field: "mismatched-id"}
    return EvidencePersistenceRequest(**payload, promotion_result=request.promotion_result,
                                      persistence_request_id=_digest(payload))


def _store(path, logical_store_id="test-store"):
    return EvidenceStore(path, logical_store_id=logical_store_id)


def test_persistence_is_idempotent_round_trips_and_keeps_actor_distinct(tmp_path):
    request = _request()
    before = request.promotion_result.evidence_item.canonical_json()
    with _store(tmp_path / "evidence.duckdb") as store:
        first = persist_promoted_evidence(request, store)
        second = persist_promoted_evidence(request, store)
        stored = store.get_item(request.evidence_item_id)
        assert (first.status, first.persisted, first.new_write) == ("persisted", True, True)
        assert (second.status, second.persisted, second.new_write) == ("already_persisted", True, False)
        assert first.persistence_receipt_id != second.persistence_receipt_id
        assert len(store.list_items()) == 1
        assert stored.canonical_json() == before
        details = stored.provenance_history[0].details
        assert details["human_review_packet_id"] == first.packet_id
        assert details["human_review_decision_id"] == first.review_decision_id
        assert first.persistence_actor_id == "operator-001"
        assert first.persistence_actor_id != details["curator_id"]
    assert request.promotion_result.evidence_item.canonical_json() == before


@pytest.mark.parametrize("status", ["rejected_by_reviewer", "deferred_by_reviewer", "blocked_by_audit", "invalid_review"])
def test_non_promoted_results_are_ineligible_and_never_written(tmp_path, status):
    with _store(tmp_path / "evidence.duckdb") as store:
        receipt = persist_promoted_evidence(_request(_promotion(status)), store)
        assert receipt.status == "not_promoted"
        assert receipt.persisted is False
        assert store.list_items() == []


def test_persisted_input_missing_item_and_invalid_evidence_fail_closed(tmp_path):
    persisted = _request(_promotion(persisted=True))
    missing_result = _promotion()
    object.__setattr__(missing_result, "evidence_item", None)
    missing = _request(missing_result)
    bad_result = _promotion()
    object.__setattr__(bad_result, "evidence_item", replace(bad_result.evidence_item, observation=""))
    bad = _request(bad_result)
    with _store(tmp_path / "evidence.duckdb") as store:
        assert persist_promoted_evidence(persisted, store).status == "invalid_promotion"
        assert persist_promoted_evidence(missing, store).status == "missing_evidence_item"
        assert persist_promoted_evidence(bad, store).status == "evidence_validation_failed"
        assert store.list_items() == []


@pytest.mark.parametrize("field", ["promotion_result_id", "evidence_item_id", "review_decision_id", "audit_result_id", "candidate_id"])
def test_request_identity_chain_mismatches_are_rejected(tmp_path, field):
    request = _mismatched_request(_request(), field)
    with _store(tmp_path / "evidence.duckdb") as store:
        receipt = persist_promoted_evidence(request, store)
        assert receipt.status == "identity_mismatch"
        assert receipt.persisted is False
        assert store.list_items() == []


def test_invalid_promotion_and_missing_chain_ids_are_rejected(tmp_path):
    request = _request()
    object.__setattr__(request.promotion_result, "promotion_result_id", "wrong")
    with _store(tmp_path / "evidence.duckdb") as store:
        assert persist_promoted_evidence(request, store).status == "identity_mismatch"
    request = _request()
    object.__setattr__(request.promotion_result, "packet_id", None)
    with _store(tmp_path / "other.duckdb") as store:
        assert persist_promoted_evidence(request, store).status == "identity_mismatch"


def test_schema_mismatch_content_conflict_and_append_only_behavior(tmp_path):
    request = _request()
    incompatible = _request(expected_store_schema_version="unknown-store-schema")
    with _store(tmp_path / "evidence.duckdb") as store:
        assert persist_promoted_evidence(incompatible, store).status == "store_schema_mismatch"
        assert persist_promoted_evidence(request, store).status == "persisted"
        original = store.get_item(request.evidence_item_id).canonical_json()
        object.__setattr__(request.promotion_result, "evidence_item", replace(
            request.promotion_result.evidence_item, observation="Changed content."))
        receipt = persist_promoted_evidence(request, store)
        assert (receipt.status, receipt.persisted, receipt.new_write, receipt.codes) == (
            "content_conflict", False, False, ("existing_payload_mismatch",))
        assert store.get_item(request.evidence_item_id).canonical_json() == original
        assert len(store.list_items()) == 1


def test_logical_store_identity_is_explicit_and_mismatches_fail_closed(tmp_path):
    request = _request()
    with _store(tmp_path / "evidence.duckdb", "other-store") as store:
        receipt = persist_promoted_evidence(request, store)
        assert (receipt.status, receipt.persisted, receipt.codes) == (
            "invalid_request", False, ("store_logical_identity_mismatch",))
        assert store.list_items() == []
    with EvidenceStore(tmp_path / "unidentified.duckdb") as store:
        receipt = persist_promoted_evidence(request, store)
        assert (receipt.status, receipt.persisted, receipt.codes) == (
            "invalid_request", False, ("store_logical_identity_mismatch",))
        assert store.list_items() == []


def test_store_write_failure_is_sanitized_and_does_not_leak_source_or_traceback(tmp_path, monkeypatch):
    request = _request()
    with _store(tmp_path / "evidence.duckdb") as store:
        def fail(_item):
            raise StorageIntegrityError("postgres://user:password@example/secret source traceback")
        monkeypatch.setattr(store, "insert_finalized_item", fail)
        receipt = persist_promoted_evidence(request, store)
    text = receipt.canonical_json()
    assert receipt.status == "store_write_failed"
    assert receipt.codes == ("store_operation_failed",)
    assert all(term not in text for term in ("postgres", "password", "traceback", request.promotion_result.evidence_item.quoted_span))


def test_unexpected_store_write_failure_is_sanitized_and_fails_closed(tmp_path, monkeypatch):
    request = _request()
    with _store(tmp_path / "evidence.duckdb") as store:
        def fail(_item):
            raise RuntimeError("postgres://user:password@example/secret source traceback")
        monkeypatch.setattr(store, "insert_finalized_item", fail)
        receipt = persist_promoted_evidence(request, store)
        assert store.list_items() == []
    text = receipt.canonical_json()
    assert (receipt.status, receipt.persisted, receipt.new_write, receipt.codes) == (
        "store_write_failed", False, False, ("store_operation_failed",))
    assert all(term not in text for term in ("postgres", "password", "traceback", request.promotion_result.evidence_item.quoted_span))


def test_round_trip_mismatch_fails_closed_with_sanitized_code(tmp_path, monkeypatch):
    request = _request()
    with _store(tmp_path / "evidence.duckdb") as store:
        original_get = store.get_item
        calls = 0
        def mismatching_get(evidence_id):
            nonlocal calls
            calls += 1
            item = original_get(evidence_id)
            return item if calls != 2 or item is None else replace(item, observation="Different but valid.")
        monkeypatch.setattr(store, "get_item", mismatching_get)
        receipt = persist_promoted_evidence(request, store)
        assert receipt.status == "round_trip_verification_failed"
        assert receipt.persisted is False
        assert receipt.codes == ("round_trip_payload_mismatch",)


def test_invalid_request_and_existing_store_records_remain_readable(tmp_path):
    with _store(tmp_path / "evidence.duckdb") as store:
        assert persist_promoted_evidence(object(), store).status == "invalid_request"
        request = _request()
        assert persist_promoted_evidence(request, store).status == "persisted"
        assert store.get_item(request.evidence_item_id) is not None

"""Explicit, idempotent persistence service for Issue 306 promotion results."""

from __future__ import annotations

from hashlib import sha256
from typing import Any

from targetintel.llm.contracts import canonical_json
from targetintel.llm.evidence_promotion import EvidencePromotionResult, PROMOTION_FORMAT_VERSION

from .models import EvidenceItem
from .persistence_models import (EvidencePersistenceReceipt, EvidencePersistenceRequest,
    PERSISTENCE_REQUEST_FORMAT_VERSION, make_receipt)
from .store import SCHEMA_VERSION, EvidenceStore, HashCollisionError, ImmutableEvidenceError
from .validation import ValidationError, require_finalizable


def _hash(value: Any) -> str:
    return sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _payload_hash(item: EvidenceItem) -> str:
    return sha256(item.canonical_json().encode("utf-8")).hexdigest()


def _context(request: EvidencePersistenceRequest | object) -> dict[str, Any]:
    if not isinstance(request, EvidencePersistenceRequest):
        return {key: None for key in ("persistence_request_id", "logical_store_id", "promotion_result_id",
            "review_decision_id", "audit_result_id", "candidate_id", "evidence_item_id", "persistence_actor_id")}
    return {"persistence_request_id": request.persistence_request_id,
        "logical_store_id": request.logical_store_id, "promotion_result_id": request.promotion_result_id,
        "review_decision_id": request.review_decision_id, "audit_result_id": request.audit_result_id,
        "candidate_id": request.candidate_id, "evidence_item_id": request.evidence_item_id,
        "persistence_actor_id": request.persistence_actor_id}


def _receipt(request: EvidencePersistenceRequest | object, status: str, *, codes: tuple[str, ...] = (),
             idempotency_key: str | None = None, store_schema_version: str | None = None,
             payload_hash: str | None = None, new_write: bool = False) -> EvidencePersistenceReceipt:
    data = _context(request)
    result = request.promotion_result if isinstance(request, EvidencePersistenceRequest) else None
    return make_receipt(**data, status=status, idempotency_key=idempotency_key,
        store_schema_version=store_schema_version, canonical_stored_payload_hash=payload_hash,
        packet_id=result.packet_id if isinstance(result, EvidencePromotionResult) else None,
        card_id=result.card_id if isinstance(result, EvidencePromotionResult) else None,
        new_write=new_write, persisted=status in {"persisted", "already_persisted"}, codes=codes)


def _promotion_identity_valid(result: EvidencePromotionResult) -> bool:
    return (result.promotion_format_version == PROMOTION_FORMAT_VERSION
        and result.promotion_result_id == _hash(result.identity_payload()))


def _provenance_valid(item: EvidenceItem, request: EvidencePersistenceRequest) -> bool:
    """Verify the immutable IDs retained in Issue 306's manual-review step."""
    result = request.promotion_result
    steps = [step for step in item.provenance_history if step.step_type == "manual_review"]
    if len(steps) != 1:
        return False
    details = steps[0].details
    required = ("human_review_packet_id", "human_review_decision_id", "candidate_id", "card_id",
                "audit_result_id", "source_document_id", "source_content_hash", "curator_id")
    if any(not isinstance(details.get(key), str) or not details[key].strip() for key in required):
        return False
    source_hash = details["source_content_hash"]
    return (len(source_hash) == 64 and all(ch in "0123456789abcdef" for ch in source_hash)
        and details["human_review_packet_id"] == result.packet_id
        and details["human_review_decision_id"] == result.review_decision_id
        and details["candidate_id"] == result.candidate_id
        and details["card_id"] == result.card_id
        and details["audit_result_id"] == result.audit_result_id
        and details["curator_id"] == result.reviewer_id)


def _item_identity_valid(item: EvidenceItem, request: EvidencePersistenceRequest) -> bool:
    result = request.promotion_result
    mapping = {name: getattr(item, name) for name in EvidenceItem.__dataclass_fields__
               if name not in {"evidence_id", "record_hash", "quoted_span", "provenance_history"}}
    expected = _hash({"candidate_id": result.candidate_id,
                      "review_decision_id": result.review_decision_id, "mapping": mapping})
    return item.evidence_id == expected


def _idempotency_key(request: EvidencePersistenceRequest, payload_hash: str) -> str:
    return _hash({"request_format_version": PERSISTENCE_REQUEST_FORMAT_VERSION,
        "promotion_result_id": request.promotion_result_id, "evidence_item_id": request.evidence_item_id,
        "review_decision_id": request.review_decision_id, "logical_store_id": request.logical_store_id,
        "canonical_evidence_payload_hash": payload_hash})


def persist_promoted_evidence(request: EvidencePersistenceRequest, store: EvidenceStore) -> EvidencePersistenceReceipt:
    """Persist one eligible promoted item using the existing immutable store API.

    This function performs no discovery, provider calls, retrieval, scoring, or
    retries.  It never modifies its request, promotion result, or EvidenceItem.
    """
    if not isinstance(request, EvidencePersistenceRequest):
        return _receipt(request, "invalid_request", codes=("persistence_request_invalid",))
    if not isinstance(store, EvidenceStore):
        return _receipt(request, "invalid_request", codes=("store_contract_invalid",))
    if store.logical_store_id != request.logical_store_id:
        return _receipt(request, "invalid_request", codes=("store_logical_identity_mismatch",),
                        store_schema_version=SCHEMA_VERSION)
    if request.expected_store_schema_version not in (None, SCHEMA_VERSION):
        return _receipt(request, "store_schema_mismatch", codes=("store_schema_incompatible",),
                        store_schema_version=SCHEMA_VERSION)
    result = request.promotion_result
    if not isinstance(result, EvidencePromotionResult):
        return _receipt(request, "invalid_promotion", codes=("promotion_contract_invalid",), store_schema_version=SCHEMA_VERSION)
    if not _promotion_identity_valid(result):
        return _receipt(request, "identity_mismatch", codes=("promotion_identity_mismatch",), store_schema_version=SCHEMA_VERSION)
    if result.status != "promoted":
        return _receipt(request, "not_promoted", codes=("promotion_status_not_promoted",), store_schema_version=SCHEMA_VERSION)
    if result.persisted:
        return _receipt(request, "invalid_promotion", codes=("promotion_persisted_flag_invalid",), store_schema_version=SCHEMA_VERSION)
    item = result.evidence_item
    if item is None:
        return _receipt(request, "missing_evidence_item", codes=("promotion_evidence_item_missing",), store_schema_version=SCHEMA_VERSION)
    if not isinstance(item, EvidenceItem) or result.evidence_item_id != item.evidence_id:
        return _receipt(request, "identity_mismatch", codes=("promotion_evidence_identity_mismatch",), store_schema_version=SCHEMA_VERSION)
    if (request.promotion_result_id != result.promotion_result_id or request.evidence_item_id != item.evidence_id
            or request.review_decision_id != result.review_decision_id or request.audit_result_id != result.audit_result_id
            or request.candidate_id != result.candidate_id):
        return _receipt(request, "identity_mismatch", codes=("request_promotion_identity_mismatch",), store_schema_version=SCHEMA_VERSION)
    if not all((result.review_decision_id, result.packet_id, result.audit_result_id, result.card_id,
                result.candidate_id, result.reviewer_id)):
        return _receipt(request, "identity_mismatch", codes=("promotion_identity_chain_missing",), store_schema_version=SCHEMA_VERSION)
    if not _provenance_valid(item, request):
        return _receipt(request, "identity_mismatch", codes=("provenance_or_evidence_identity_mismatch",), store_schema_version=SCHEMA_VERSION)
    try:
        require_finalizable(item)
        finalized = item.with_calculated_record_hash()
    except (ValidationError, TypeError, ValueError):
        return _receipt(request, "evidence_validation_failed", codes=("evidence_item_validation_failed",), store_schema_version=SCHEMA_VERSION)
    payload_hash = _payload_hash(finalized)
    key = _idempotency_key(request, payload_hash)
    try:
        existing = store.get_item(finalized.evidence_id)
    except Exception:
        return _receipt(request, "store_write_failed", codes=("store_operation_failed",), idempotency_key=key,
                        store_schema_version=SCHEMA_VERSION, payload_hash=payload_hash)
    if existing is not None:
        if _payload_hash(existing) != payload_hash:
            return _receipt(request, "content_conflict", codes=("existing_payload_mismatch",), idempotency_key=key,
                            store_schema_version=SCHEMA_VERSION, payload_hash=payload_hash)
        if not _item_identity_valid(item, request):
            return _receipt(request, "identity_mismatch", codes=("provenance_or_evidence_identity_mismatch",),
                            idempotency_key=key, store_schema_version=SCHEMA_VERSION, payload_hash=payload_hash)
        return _receipt(request, "already_persisted", idempotency_key=key, store_schema_version=SCHEMA_VERSION,
                        payload_hash=payload_hash)
    if not _item_identity_valid(item, request):
        return _receipt(request, "identity_mismatch", codes=("provenance_or_evidence_identity_mismatch",),
                        idempotency_key=key, store_schema_version=SCHEMA_VERSION, payload_hash=payload_hash)
    try:
        inserted = store.insert_finalized_item(finalized)
    except (HashCollisionError, ImmutableEvidenceError):
        try:
            current = store.get_item(finalized.evidence_id)
        except Exception:
            return _receipt(request, "store_write_failed", codes=("store_operation_failed",), idempotency_key=key,
                            store_schema_version=SCHEMA_VERSION, payload_hash=payload_hash)
        if current is not None and _payload_hash(current) != payload_hash:
            return _receipt(request, "content_conflict", codes=("existing_payload_mismatch",), idempotency_key=key,
                            store_schema_version=SCHEMA_VERSION, payload_hash=payload_hash)
        return _receipt(request, "store_write_failed", codes=("store_operation_failed",), idempotency_key=key,
                        store_schema_version=SCHEMA_VERSION, payload_hash=payload_hash)
    except Exception:
        return _receipt(request, "store_write_failed", codes=("store_operation_failed",), idempotency_key=key,
                        store_schema_version=SCHEMA_VERSION, payload_hash=payload_hash)
    if not inserted.inserted:
        current = store.get_item(finalized.evidence_id)
        if current is not None and _payload_hash(current) == payload_hash:
            return _receipt(request, "already_persisted", idempotency_key=key, store_schema_version=SCHEMA_VERSION,
                            payload_hash=payload_hash)
        return _receipt(request, "content_conflict", codes=("existing_payload_mismatch",), idempotency_key=key,
                        store_schema_version=SCHEMA_VERSION, payload_hash=payload_hash)
    stored = store.get_item(finalized.evidence_id)
    if stored is None or _payload_hash(stored) != payload_hash or not _provenance_valid(stored, request):
        return _receipt(request, "round_trip_verification_failed", codes=("round_trip_payload_mismatch",),
                        idempotency_key=key, store_schema_version=SCHEMA_VERSION, payload_hash=payload_hash)
    return _receipt(request, "persisted", idempotency_key=key, store_schema_version=SCHEMA_VERSION,
                    payload_hash=payload_hash, new_write=True)

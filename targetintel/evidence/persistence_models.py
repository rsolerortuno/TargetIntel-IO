"""Immutable contracts for explicit reviewed-evidence persistence.

These contracts deliberately carry references to the Issue 306 promotion
result rather than recreating promotion, review, or scientific validation.
Operational timestamps are retained separately from deterministic identities.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
from types import MappingProxyType
from typing import Any, Mapping

from targetintel.llm.contracts import canonical_json
from targetintel.llm.evidence_promotion import EvidencePromotionResult
from targetintel.llm.review_schema import reject_unsafe


PERSISTENCE_REQUEST_FORMAT_VERSION = "reviewed-evidence-persistence-request-v1"
PERSISTENCE_RECEIPT_FORMAT_VERSION = "reviewed-evidence-persistence-receipt-v1"
PERSISTENCE_STATUSES = frozenset({
    "persisted", "already_persisted", "not_promoted", "missing_evidence_item",
    "invalid_promotion", "identity_mismatch", "evidence_validation_failed",
    "store_schema_mismatch", "content_conflict", "round_trip_verification_failed",
    "store_write_failed", "invalid_request",
})


def _nonempty(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return value


def _utc(value: datetime | None, name: str) -> datetime | None:
    if value is None:
        return None
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")
    return value.astimezone(timezone.utc)


def _digest(value: Mapping[str, Any]) -> str:
    return sha256(canonical_json(value).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class EvidencePersistenceRequest:
    """One explicit operator request to persist one promoted EvidenceItem."""

    request_format_version: str
    persistence_request_id: str
    promotion_result: EvidencePromotionResult
    promotion_result_id: str
    evidence_item_id: str
    review_decision_id: str
    audit_result_id: str
    candidate_id: str
    persistence_actor_id: str
    logical_store_id: str
    expected_store_schema_version: str | None = None
    requested_at: datetime | None = None

    def __post_init__(self) -> None:
        if self.request_format_version != PERSISTENCE_REQUEST_FORMAT_VERSION:
            raise ValueError("unknown persistence request format version")
        if not isinstance(self.promotion_result, EvidencePromotionResult):
            raise ValueError("promotion_result must be an EvidencePromotionResult")
        for field in ("persistence_request_id", "promotion_result_id", "evidence_item_id",
                      "review_decision_id", "audit_result_id", "candidate_id",
                      "persistence_actor_id", "logical_store_id"):
            _nonempty(getattr(self, field), field)
        if self.expected_store_schema_version is not None:
            _nonempty(self.expected_store_schema_version, "expected_store_schema_version")
        object.__setattr__(self, "requested_at", _utc(self.requested_at, "requested_at"))
        if self.persistence_request_id != _digest(self.identity_payload()):
            raise ValueError("persistence request identity does not match payload")

    def identity_payload(self) -> dict[str, Any]:
        return {
            "request_format_version": self.request_format_version,
            "promotion_result_id": self.promotion_result_id,
            "evidence_item_id": self.evidence_item_id,
            "review_decision_id": self.review_decision_id,
            "audit_result_id": self.audit_result_id,
            "candidate_id": self.candidate_id,
            "persistence_actor_id": self.persistence_actor_id,
            "logical_store_id": self.logical_store_id,
            "expected_store_schema_version": self.expected_store_schema_version,
        }

    def to_dict(self) -> dict[str, Any]:
        data = self.identity_payload() | {
            "persistence_request_id": self.persistence_request_id,
            "promotion_result": self.promotion_result.to_dict(),
        }
        if self.requested_at is not None:
            data["requested_at"] = self.requested_at.isoformat(timespec="microseconds").replace("+00:00", "Z")
        return data

    def canonical_json(self) -> str:
        return canonical_json(self.to_dict())

    @classmethod
    def create(cls, *, promotion_result: EvidencePromotionResult, persistence_actor_id: str,
               logical_store_id: str, expected_store_schema_version: str | None = None,
               requested_at: datetime | None = None) -> "EvidencePersistenceRequest":
        if not isinstance(promotion_result, EvidencePromotionResult):
            raise ValueError("promotion_result must be an EvidencePromotionResult")
        payload = {
            "request_format_version": PERSISTENCE_REQUEST_FORMAT_VERSION,
            "promotion_result_id": promotion_result.promotion_result_id,
            "evidence_item_id": promotion_result.evidence_item_id or "",
            "review_decision_id": promotion_result.review_decision_id or "",
            "audit_result_id": promotion_result.audit_result_id or "",
            "candidate_id": promotion_result.candidate_id,
            "persistence_actor_id": persistence_actor_id,
            "logical_store_id": logical_store_id,
            "expected_store_schema_version": expected_store_schema_version,
        }
        return cls(**payload, persistence_request_id=_digest(payload), promotion_result=promotion_result,
                   requested_at=requested_at)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "EvidencePersistenceRequest":
        allowed = frozenset({"request_format_version", "persistence_request_id", "promotion_result",
            "promotion_result_id", "evidence_item_id", "review_decision_id", "audit_result_id",
            "candidate_id", "persistence_actor_id", "logical_store_id", "expected_store_schema_version",
            "requested_at"})
        if not isinstance(data, Mapping) or set(data) - allowed:
            raise ValueError("unknown persistence request field")
        required = allowed - {"expected_store_schema_version", "requested_at"}
        if required - set(data):
            raise ValueError("missing required persistence request field")
        # A promotion result is intentionally not parsed here: Issue 306 owns
        # its strict construction boundary and callers pass that immutable object.
        # It is therefore excluded from this JSON-like request-field scan.
        # All caller-controlled serialized fields remain subject to the same
        # secret and hidden-reasoning boundary as human review inputs.
        reject_unsafe({key: value for key, value in data.items() if key != "promotion_result"})
        if not isinstance(data.get("promotion_result"), EvidencePromotionResult):
            raise ValueError("promotion_result must be an EvidencePromotionResult")
        values = dict(data)
        requested_at = values.get("requested_at")
        if isinstance(requested_at, str):
            try:
                values["requested_at"] = datetime.fromisoformat(requested_at.replace("Z", "+00:00"))
            except ValueError as exc:
                raise ValueError("requested_at must be an ISO-8601 timestamp") from exc
        return cls(**values)


@dataclass(frozen=True)
class EvidencePersistenceReceipt:
    """Sanitized immutable outcome of one persistence attempt."""

    receipt_format_version: str
    persistence_receipt_id: str
    persistence_request_id: str | None
    idempotency_key: str | None
    status: str
    logical_store_id: str | None
    store_schema_version: str | None
    evidence_item_id: str | None
    promotion_result_id: str | None
    review_decision_id: str | None
    packet_id: str | None
    audit_result_id: str | None
    card_id: str | None
    candidate_id: str | None
    persistence_actor_id: str | None
    canonical_stored_payload_hash: str | None
    new_write: bool
    persisted: bool
    codes: tuple[str, ...] = ()
    persisted_at: datetime | None = None
    persistence_scope: str = "Persistence records controlled storage only; it does not imply scientific or clinical validation."

    def __post_init__(self) -> None:
        if self.receipt_format_version != PERSISTENCE_RECEIPT_FORMAT_VERSION:
            raise ValueError("unknown persistence receipt format version")
        if self.status not in PERSISTENCE_STATUSES:
            raise ValueError("unknown persistence status")
        if self.persisted != (self.status in {"persisted", "already_persisted"}):
            raise ValueError("persisted flag is inconsistent with status")
        if self.new_write and self.status != "persisted":
            raise ValueError("new writes require persisted status")
        if self.status == "already_persisted" and self.new_write:
            raise ValueError("already persisted cannot be a new write")
        codes = tuple(sorted(set(self.codes)))
        if any(not isinstance(code, str) or not code for code in codes):
            raise ValueError("receipt codes must be non-empty strings")
        object.__setattr__(self, "codes", codes)
        object.__setattr__(self, "persisted_at", _utc(self.persisted_at, "persisted_at"))
        if self.persistence_receipt_id != _digest(self.identity_payload()):
            raise ValueError("persistence receipt identity does not match payload")

    def identity_payload(self) -> dict[str, Any]:
        return {"receipt_format_version": self.receipt_format_version,
            "persistence_request_id": self.persistence_request_id, "idempotency_key": self.idempotency_key,
            "status": self.status, "logical_store_id": self.logical_store_id,
            "store_schema_version": self.store_schema_version, "evidence_item_id": self.evidence_item_id,
            "promotion_result_id": self.promotion_result_id, "review_decision_id": self.review_decision_id,
            "packet_id": self.packet_id, "audit_result_id": self.audit_result_id,
            "card_id": self.card_id, "candidate_id": self.candidate_id,
            "persistence_actor_id": self.persistence_actor_id,
            "canonical_stored_payload_hash": self.canonical_stored_payload_hash,
            "new_write": self.new_write, "persisted": self.persisted, "codes": list(self.codes),
            "persistence_scope": self.persistence_scope}

    def to_dict(self) -> dict[str, Any]:
        data = self.identity_payload() | {"persistence_receipt_id": self.persistence_receipt_id}
        if self.persisted_at is not None:
            data["persisted_at"] = self.persisted_at.isoformat(timespec="microseconds").replace("+00:00", "Z")
        return data

    def canonical_json(self) -> str:
        return canonical_json(self.to_dict())


def make_receipt(**values: Any) -> EvidencePersistenceReceipt:
    """Build a receipt while keeping its deterministic ID internal to callers."""
    payload = dict(values)
    payload.setdefault("receipt_format_version", PERSISTENCE_RECEIPT_FORMAT_VERSION)
    payload.setdefault("codes", ())
    payload["codes"] = tuple(sorted(set(payload["codes"])))
    payload.setdefault("persistence_scope", "Persistence records controlled storage only; it does not imply scientific or clinical validation.")
    identity = {key: payload.get(key) for key in (
        "receipt_format_version", "persistence_request_id", "idempotency_key", "status",
        "logical_store_id", "store_schema_version", "evidence_item_id", "promotion_result_id",
        "review_decision_id", "packet_id", "audit_result_id", "card_id", "candidate_id",
        "persistence_actor_id", "canonical_stored_payload_hash", "new_write", "persisted",
        "persistence_scope")}
    identity["codes"] = list(payload["codes"])
    return EvidencePersistenceReceipt(persistence_receipt_id=_digest(identity), **payload)

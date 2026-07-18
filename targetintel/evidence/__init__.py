"""Typed contracts and optional immutable storage for the evidence layer."""

from .models import EvidenceItem, ProvenanceStep, RetrievalAttempt
from .store import EvidenceStore, HashCollisionError, ImmutableEvidenceError, InsertResult
from .validation import (
    SemanticValidationContext,
    ValidationError,
    ValidationIssue,
    require_semantically_valid,
    validate_semantic,
)
from .verifier import CitationVerifier, EvidenceFinalizer, FrozenSourceContent
from .duplicates import DuplicateDecision, TrueDuplicateDetector
from .independence import EvidenceIndependenceGrouper, assign_family, independent_family_ids

__all__ = [
    "EvidenceItem",
    "ProvenanceStep",
    "RetrievalAttempt",
    "EvidenceStore",
    "HashCollisionError",
    "ImmutableEvidenceError",
    "InsertResult",
    "SemanticValidationContext",
    "ValidationError",
    "ValidationIssue",
    "require_semantically_valid",
    "validate_semantic",
    "CitationVerifier",
    "EvidenceFinalizer",
    "FrozenSourceContent",
    "DuplicateDecision",
    "TrueDuplicateDetector",
    "EvidenceIndependenceGrouper",
    "assign_family",
    "independent_family_ids",
    "EvidencePersistenceRequest",
    "EvidencePersistenceReceipt",
    "persist_promoted_evidence",
]


def __getattr__(name: str):
    """Expose persistence contracts without disturbing the existing LLM import cycle."""
    if name in {"EvidencePersistenceRequest", "EvidencePersistenceReceipt"}:
        from .persistence_models import EvidencePersistenceReceipt, EvidencePersistenceRequest
        return {"EvidencePersistenceRequest": EvidencePersistenceRequest,
                "EvidencePersistenceReceipt": EvidencePersistenceReceipt}[name]
    if name == "persist_promoted_evidence":
        from .reviewed_persistence import persist_promoted_evidence
        return persist_promoted_evidence
    raise AttributeError(name)

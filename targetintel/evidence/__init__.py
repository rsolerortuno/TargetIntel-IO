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
]

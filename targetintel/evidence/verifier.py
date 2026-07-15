"""Offline literal citation verification and staged-candidate finalization."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from typing import Mapping, Sequence

from .duplicates import DuplicateDecision, TrueDuplicateDetector
from .independence import EvidenceIndependenceGrouper
from .models import EvidenceItem, ProvenanceStep
from .validation import SemanticValidationContext, require_semantically_valid, require_valid


_GENERIC = frozenset({"unknown", "none", "null", "missing", "n/a", "na", "unspecified", "unavailable", "not_applicable", "not available"})


@dataclass(frozen=True)
class FrozenSourceContent:
    """Injected source material used by the verifier; it has no I/O behavior."""
    source: str
    source_id: str
    source_text: str | None = None
    document_location: str | None = None


@dataclass(frozen=True)
class VerificationResult:
    item: EvidenceItem
    success: bool
    reason: str | None


@dataclass(frozen=True)
class FinalizationResult:
    item: EvidenceItem
    verification: VerificationResult
    duplicate: DuplicateDecision


def _stable(value: str | None) -> bool:
    return isinstance(value, str) and bool(value.strip()) and value.strip().lower() not in _GENERIC


def _computed_or_database(item: EvidenceItem) -> bool:
    return item.extraction_method in {"computed", "database_import"} or item.evidence_type == "database_assertion"


class CitationVerifier:
    """Verify supplied frozen content with an exact, case-sensitive substring test."""

    def __init__(self, *, recorded_at: datetime | None = None) -> None:
        self._recorded_at = recorded_at

    def verify(self, item: EvidenceItem, document: FrozenSourceContent | object) -> VerificationResult:
        source = getattr(document, "source", None)
        source_id = getattr(document, "source_id", None)
        source_text = getattr(document, "source_text", None)
        document_location = item.document_location or getattr(document, "document_location", None)
        recorded_at = self._recorded_at or item.retrieved_at
        reason: str | None = None
        if not _stable(item.source) or not _stable(item.source_id):
            reason = "stable source identity is required"
        elif source != item.source or source_id != item.source_id:
            reason = "frozen document identity does not match evidence source identity"
        elif _computed_or_database(item):
            if not isinstance(item.computed_support, str) or not item.computed_support.strip():
                reason = "computed or database evidence requires non-empty computed_support"
        elif not isinstance(item.quoted_span, str) or not item.quoted_span:
            reason = "literature evidence requires a non-empty quoted_span"
        elif not isinstance(source_text, str):
            reason = "frozen document text is required for literature verification"
        elif item.quoted_span not in source_text:
            reason = "quoted_span is not contained literally in frozen document text"
        success = reason is None
        details: dict[str, object] = {
            "success": success,
            "verification_kind": "computed_support" if _computed_or_database(item) else "literal_quoted_span",
            "source": item.source,
            "source_id": item.source_id,
            "document_location": document_location,
        }
        if reason is not None:
            details["reason"] = reason
        verified = replace(
            item,
            validation_status="citation_verified" if success else "citation_unverified",
            document_location=document_location,
            provenance_history=(*item.provenance_history, ProvenanceStep("citation_verification", recorded_at, details)),
        )
        return VerificationResult(verified, success, reason)


class EvidenceFinalizer:
    """Complete the in-memory, deterministic finalization sequence.

    It never inserts into storage.  Callers pass its returned, hash-complete
    item to ``EvidenceStore.insert_finalized_item`` exactly once.
    """

    def __init__(self, verifier: CitationVerifier | None = None) -> None:
        self._verifier = verifier or CitationVerifier()
        self._grouper = EvidenceIndependenceGrouper()
        self._duplicates = TrueDuplicateDetector()

    def finalize(
        self,
        candidate: EvidenceItem,
        document: FrozenSourceContent | object,
        *,
        existing: Sequence[EvidenceItem] = (),
        context: Mapping[str, EvidenceItem] | None = None,
    ) -> FinalizationResult:
        require_valid(candidate)
        semantic_context = SemanticValidationContext(context or {item.evidence_id: item for item in existing})
        require_semantically_valid(candidate, semantic_context)
        verification = self._verifier.verify(candidate, document)
        assigned = self._grouper.assign_family(verification.item, semantic_context.evidence_items)
        final_context = SemanticValidationContext({**semantic_context.evidence_items, assigned.evidence_id: assigned})
        finalized = assigned.with_calculated_record_hash(final_context)
        duplicate = self._duplicates.assess(finalized, existing, final_context)
        return FinalizationResult(finalized, VerificationResult(finalized, verification.success, verification.reason), duplicate)

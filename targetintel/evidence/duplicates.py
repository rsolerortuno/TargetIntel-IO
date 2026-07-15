"""True exact-duplicate assessment without family-based record selection."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from .models import EvidenceItem
from .validation import SemanticValidationContext


@dataclass(frozen=True)
class DuplicateDecision:
    is_duplicate: bool
    existing_evidence_id: str | None
    rationale: str


class TrueDuplicateDetector:
    """Recognize only identical finalized canonical content.

    This intentionally does not use family, publication, cohort, or source as
    a proxy for duplication.  Storage remains responsible for collision
    handling, because a collision is an integrity error, not a duplicate.
    """

    def assess(
        self,
        candidate: EvidenceItem,
        existing: Sequence[EvidenceItem],
        context: SemanticValidationContext | None = None,
    ) -> DuplicateDecision:
        candidate_hash = candidate.calculate_record_hash(context)
        candidate_canonical = candidate.canonical_json()
        for record in sorted(existing, key=lambda value: value.evidence_id):
            record_hash = record.calculate_record_hash(context)
            if record_hash != candidate_hash:
                continue
            if record.canonical_json() != candidate_canonical:
                raise RuntimeError("record hash collision with distinct canonical content")
            return DuplicateDecision(
                True,
                record.evidence_id,
                "exact finalized canonical record hash and canonical content match",
            )
        return DuplicateDecision(False, None, "no exact finalized canonical content match")


def assess_duplicate(candidate: EvidenceItem, existing: Sequence[EvidenceItem], context: SemanticValidationContext | None = None) -> DuplicateDecision:
    return TrueDuplicateDetector().assess(candidate, existing, context)

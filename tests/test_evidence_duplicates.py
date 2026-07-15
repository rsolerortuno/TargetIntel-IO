"""True-duplicate tests: exact content only, no family selection."""

from __future__ import annotations

from dataclasses import replace

import pytest

from targetintel.evidence.duplicates import TrueDuplicateDetector
from tests.test_evidence_models import evidence_item


def finalized(**changes: object):
    return evidence_item(**changes).with_calculated_record_hash()


def test_exact_content_is_duplicate_with_an_auditable_rationale() -> None:
    first = finalized()
    decision = TrueDuplicateDetector().assess(replace(first, evidence_id="repeat", record_hash=None).with_calculated_record_hash(), [first])
    assert decision.is_duplicate and decision.existing_evidence_id == first.evidence_id
    assert "exact" in decision.rationale


def test_same_source_shared_family_and_shared_publication_are_not_duplicate_proxies() -> None:
    first = finalized(
        publication_id="PMID:1", experiment_id="experiment-a", patient_cohort_id="cohort",
        evidence_family="efam-v1:shared", evidence_family_basis="patient_cohort_id",
        independence_eligible=True, independence_ineligibility_reason=None, quoted_span="first span",
    )
    detector = TrueDuplicateDetector()
    for changed in (
        replace(first, evidence_id="observation", observation="different observation", record_hash=None),
        replace(first, evidence_id="quote", quoted_span="different span", record_hash=None),
        replace(first, evidence_id="experiment", experiment_id="experiment-b", record_hash=None),
        replace(first, evidence_id="direction", evidence_direction="limits_target", record_hash=None),
    ):
        candidate = changed.with_calculated_record_hash()
        assert not detector.assess(candidate, [first]).is_duplicate


def test_hash_collision_is_an_integrity_error_not_a_duplicate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first = finalized(observation="first observation")
    candidate = finalized(evidence_id="collision", observation="changed observation")

    monkeypatch.setattr(type(first), "calculate_record_hash", lambda self, context=None: "collision-hash")
    with pytest.raises(RuntimeError, match="hash collision"):
        TrueDuplicateDetector().assess(candidate, [first])


def test_duplicate_assessment_never_selects_or_deletes_family_members() -> None:
    first = finalized(
        evidence_family="efam-v1:shared", evidence_family_basis="patient_cohort_id",
        independence_eligible=True, independence_ineligibility_reason=None,
    )
    second = finalized(
        evidence_id="second", observation="separate supporting observation",
        evidence_family="efam-v1:shared", evidence_family_basis="patient_cohort_id",
        independence_eligible=True, independence_ineligibility_reason=None,
    )
    candidate = finalized(
        evidence_id="candidate", observation="third separate observation",
        evidence_family="efam-v1:shared", evidence_family_basis="patient_cohort_id",
        independence_eligible=True, independence_ineligibility_reason=None,
    )
    records = [first, second]

    decision = TrueDuplicateDetector().assess(candidate, records)

    assert not decision.is_duplicate
    assert records == [first, second]

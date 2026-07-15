"""Deterministic ``efam-v1`` construction tests."""

from __future__ import annotations

from dataclasses import replace

import pytest

from targetintel.evidence.independence import EvidenceIndependenceGrouper, family_identifier, family_key
from tests.test_evidence_models import evidence_item


def root(**changes: object):
    return evidence_item(**changes)


@pytest.mark.parametrize(
    ("changes", "basis"),
    [
        ({"patient_cohort_id": "cohort", "source_dataset_id": "dataset", "experiment_id": "experiment", "publication_id": "PMID:1"}, "patient_cohort_id"),
        ({"source_dataset_id": "dataset", "experiment_id": "experiment", "publication_id": "PMID:1"}, "source_dataset_id"),
        ({"experiment_id": "experiment", "publication_id": "PMID:1"}, "experiment_id"),
        ({"publication_id": "PMID:1"}, "publication_id"),
        ({}, "stable_source_record"),
    ],
)
def test_origin_precedence(changes: dict[str, str], basis: str) -> None:
    assigned = EvidenceIndependenceGrouper().assign_family(root(**changes))
    assert assigned.evidence_family_basis == basis
    assert assigned.independence_eligible


def test_generic_origins_are_ineligible_and_key_is_deterministic() -> None:
    item = root(source=" unknown ", source_id="n/a", publication_id="missing")
    assigned = EvidenceIndependenceGrouper().assign_family(item)
    assert not assigned.independence_eligible
    assert assigned.evidence_family is None
    assert assigned.independence_ineligibility_reason

    key = family_key(root(), "publication_id", "PMID:1")
    assert family_identifier(key) == family_identifier(dict(reversed(list(key.items()))))


def test_unrelated_content_does_not_change_family() -> None:
    base = root(patient_cohort_id="cohort")
    changed = replace(
        base, observation="changed", quoted_span="changed quote", evidence_direction="limits_target",
        validation_status="rejected", extraction_confidence=0.1, retrieved_at=base.retrieved_at.replace(year=2025),
    )
    grouper = EvidenceIndependenceGrouper()
    assert grouper.assign_family(base).evidence_family == grouper.assign_family(changed).evidence_family


def test_derived_records_inherit_one_root_or_form_sorted_composite() -> None:
    grouper = EvidenceIndependenceGrouper()
    first = root(evidence_id="first", patient_cohort_id="one")
    second = root(evidence_id="second", patient_cohort_id="two")
    inherited = root(evidence_id="child", derived_from=("first",))
    composite = root(evidence_id="combined", derived_from=("second", "first"))
    one = grouper.assign_family(inherited, {"first": first})
    many = grouper.assign_family(composite, {"first": first, "second": second})

    assert one.evidence_family == grouper.assign_family(first).evidence_family
    assert many.evidence_family_basis == "composite"
    # The composite contributes no *additional* family; the inherited record
    # remains in its root family.
    assert grouper.independent_family_ids([one, many]) == {one.evidence_family}
    with pytest.raises(ValueError, match="cycle"):
        grouper.assign_family(root(evidence_id="loop", derived_from=("loop",)))
    with pytest.raises(ValueError, match="does not resolve"):
        grouper.assign_family(root(evidence_id="missing", derived_from=("absent",)))


def test_repeated_family_construction_is_byte_identical() -> None:
    grouper = EvidenceIndependenceGrouper()
    first = root(evidence_id="first", patient_cohort_id="one")
    second = root(evidence_id="second", patient_cohort_id="two")
    composite = root(evidence_id="combined", derived_from=("second", "first"))
    records = {"first": first, "second": second}

    once = grouper.assign_family(composite, records)
    again = grouper.assign_family(composite, records)

    assert once == again
    assert once.to_dict() == again.to_dict()

"""Deterministic evidence-family construction for ``efam-v1``.

This module deliberately groups records without selecting, deleting, or
otherwise preferring any member of a family.
"""

from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
from typing import Mapping, Sequence

from .models import EvidenceItem, FAMILY_ALGORITHM_VERSION, canonical_json


_GENERIC_IDENTIFIERS = frozenset({
    "unknown", "none", "null", "missing", "n/a", "na", "unspecified",
    "unavailable", "not_applicable", "not available",
})
_PRECEDENCE = (
    "patient_cohort_id", "source_dataset_id", "experiment_id", "publication_id",
)


def _normalise_identifier(value: str | None) -> str | None:
    """Perform only safe whitespace normalization, never identifier folding."""
    if not isinstance(value, str):
        return None
    normalised = value.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not normalised or normalised.lower() in _GENERIC_IDENTIFIERS:
        return None
    return normalised


def _ineligible(item: EvidenceItem, reason: str) -> EvidenceItem:
    return replace(
        item,
        evidence_family=None,
        evidence_family_algorithm_version=FAMILY_ALGORITHM_VERSION,
        evidence_family_basis="ineligible",
        independence_eligible=False,
        independence_ineligibility_reason=reason,
    )


def family_key(
    item: EvidenceItem, basis: str, origin: str | dict[str, str] | list[str],
) -> dict[str, object]:
    """Return the complete and deliberately small, hashable family key."""
    return {
        "algorithm_version": FAMILY_ALGORITHM_VERSION,
        "target_id": item.target_id,
        "disease_id": item.disease_id,
        "treatment_id": item.treatment_id,
        "family_basis": basis,
        "family_origin_id": origin,
    }


def family_identifier(key: Mapping[str, object]) -> str:
    """Return the content-addressed ``efam-v1`` identifier for ``key``."""
    return f"{FAMILY_ALGORITHM_VERSION}:" + sha256(
        canonical_json(dict(key)).encode("utf-8")
    ).hexdigest()


class EvidenceIndependenceGrouper:
    """Assign families using only explicit provenance and explicit lineage."""

    def assign_family(
        self,
        item: EvidenceItem,
        evidence_items: Mapping[str, EvidenceItem] | Sequence[EvidenceItem] = (),
    ) -> EvidenceItem:
        records = (
            dict(evidence_items)
            if isinstance(evidence_items, Mapping)
            else {record.evidence_id: record for record in evidence_items}
        )
        records[item.evidence_id] = item
        assigned: dict[str, EvidenceItem] = {}
        visiting: list[str] = []

        def resolve(record_id: str) -> EvidenceItem:
            if record_id in assigned:
                return assigned[record_id]
            if record_id not in records:
                raise ValueError(f"derived evidence parent '{record_id}' does not resolve")
            if record_id in visiting:
                cycle = " -> ".join((*visiting, record_id))
                raise ValueError(f"derived-evidence graph contains cycle: {cycle}")
            visiting.append(record_id)
            record = records[record_id]
            result = root_assignment(record) if not record.derived_from else derived_assignment(record)
            visiting.pop()
            assigned[record_id] = result
            return result

        def root_assignment(record: EvidenceItem) -> EvidenceItem:
            for basis in _PRECEDENCE:
                origin = _normalise_identifier(getattr(record, basis))
                if origin is not None:
                    return eligible(record, basis, origin)
            source = _normalise_identifier(record.source)
            source_id = _normalise_identifier(record.source_id)
            if source is not None and source_id is not None:
                return eligible(
                    record, "stable_source_record", {"source_name": source, "source_record_id": source_id}
                )
            return _ineligible(record, "no stable family origin is available")

        def derived_assignment(record: EvidenceItem) -> EvidenceItem:
            roots = root_records(record.evidence_id, ())
            root_items = [resolve(root_id) for root_id in roots]
            families = {root.evidence_family for root in root_items}
            if None in families or not all(root.independence_eligible for root in root_items):
                return _ineligible(record, "one or more derived roots are independence-ineligible")
            family_ids = sorted(family for family in families if family is not None)
            if len(family_ids) == 1:
                root = root_items[0]
                return replace(
                    record,
                    evidence_family=family_ids[0],
                    evidence_family_algorithm_version=FAMILY_ALGORITHM_VERSION,
                    evidence_family_basis=root.evidence_family_basis,
                    independence_eligible=True,
                    independence_ineligibility_reason=None,
                )
            return eligible(record, "composite", family_ids)

        def root_records(record_id: str, path: tuple[str, ...]) -> tuple[str, ...]:
            if record_id in path:
                raise ValueError("derived-evidence graph contains cycle: " + " -> ".join((*path, record_id)))
            record = records.get(record_id)
            if record is None:
                raise ValueError(f"derived evidence parent '{record_id}' does not resolve")
            if not record.derived_from:
                return (record_id,)
            roots: list[str] = []
            for parent_id in record.derived_from:
                roots.extend(root_records(parent_id, (*path, record_id)))
            return tuple(sorted(set(roots)))

        def eligible(record: EvidenceItem, basis: str, origin: str | dict[str, str] | list[str]) -> EvidenceItem:
            key = family_key(record, basis, origin)
            return replace(
                record,
                evidence_family=family_identifier(key),
                evidence_family_algorithm_version=FAMILY_ALGORITHM_VERSION,
                evidence_family_basis=basis,
                independence_eligible=True,
                independence_ineligibility_reason=None,
            )

        return resolve(item.evidence_id)

    def group(self, items: Sequence[EvidenceItem]) -> dict[str, list[EvidenceItem]]:
        """Group eligible items only; no representative is selected."""
        grouped: dict[str, list[EvidenceItem]] = {}
        for item in items:
            if item.independence_eligible and item.evidence_family is not None:
                grouped.setdefault(item.evidence_family, []).append(item)
        return {family: grouped[family] for family in sorted(grouped)}

    def independent_family_ids(self, items: Sequence[EvidenceItem]) -> set[str]:
        """Return root-family IDs, excluding ineligible and composite records."""
        return {
            item.evidence_family
            for item in items
            if item.independence_eligible
            and item.evidence_family is not None
            and item.evidence_family_basis != "composite"
        }


def assign_family(item: EvidenceItem, evidence_items: Mapping[str, EvidenceItem] | Sequence[EvidenceItem] = ()) -> EvidenceItem:
    return EvidenceIndependenceGrouper().assign_family(item, evidence_items)


def independent_family_ids(items: Sequence[EvidenceItem]) -> set[str]:
    return EvidenceIndependenceGrouper().independent_family_ids(items)

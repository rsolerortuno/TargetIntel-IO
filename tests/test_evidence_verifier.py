"""Offline literal citation-verification and finalization tests."""

from __future__ import annotations

from dataclasses import replace

import pytest

from targetintel.evidence.verifier import CitationVerifier, EvidenceFinalizer, FrozenSourceContent
from tests.test_evidence_models import evidence_item


def literature(**changes: object):
    values = dict(
        evidence_type="genetic_association",
        extraction_method="mock",
        publication_id="PMID:fixture",
        quoted_span="Literal frozen source sentence.",
        computed_support=None,
    )
    values.update(changes)
    return evidence_item(**values)


def document(text: str | None = "Literal frozen source sentence.") -> FrozenSourceContent:
    return FrozenSourceContent("Mock source", "mock-1", text, "Results")


def test_literal_quote_verification_is_exact_and_records_provenance() -> None:
    result = CitationVerifier().verify(literature(document_location="Results"), document())

    assert result.success
    assert result.item.validation_status == "citation_verified"
    assert result.item.document_location == "Results"
    assert result.item.provenance_history[-1].details["success"] is True


def test_document_location_from_frozen_content_is_retained() -> None:
    result = CitationVerifier().verify(literature(document_location=None), document())
    assert result.item.document_location == "Results"


@pytest.mark.parametrize("quote", ["literal frozen source sentence.", ""])
def test_mismatching_or_absent_quote_never_reaches_citation_verified(quote: str) -> None:
    result = CitationVerifier().verify(literature(quoted_span=quote), document())

    assert not result.success
    assert result.item.validation_status == "citation_unverified"
    assert result.item.provenance_history[-1].details["success"] is False


def test_computed_evidence_needs_support_but_never_needs_a_quote() -> None:
    computed = evidence_item(extraction_method="computed", quoted_span=None, computed_support="frozen output row")
    success = CitationVerifier().verify(computed, document(None))
    failure = CitationVerifier().verify(replace(computed, computed_support=None), document(None))

    assert success.success and success.item.validation_status == "citation_verified"
    assert not failure.success and failure.item.validation_status == "citation_unverified"


def test_computed_evidence_with_support_finalizes_as_citation_verified() -> None:
    computed = evidence_item(
        extraction_method="computed",
        quoted_span=None,
        computed_support="frozen output row",
    )

    result = EvidenceFinalizer().finalize(computed, document(None))

    assert result.verification.success
    assert result.item.validation_status == "citation_verified"
    assert result.item.quoted_span is None
    assert result.item.record_hash is not None


def test_unsuccessful_verification_can_finalize_as_auditable_unverified_record() -> None:
    result = EvidenceFinalizer().finalize(literature(), document("A different frozen sentence."))

    assert result.item.validation_status == "citation_unverified"
    assert result.item.record_hash is not None
    assert result.item.provenance_history[-1].step_type == "citation_verification"

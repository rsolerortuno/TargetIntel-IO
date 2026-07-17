"""Offline checks for the pure Issue 305 scientific claim critic."""
from dataclasses import replace
from types import MappingProxyType

import pytest

from targetintel.llm import (GroundedExtractionStatus, LLMResponse, LLMResultStatus,
    ProviderProvenance, extract_grounded_candidates)
from targetintel.llm.claim_audit import ClaimAuditFinding, ClaimBoundaryCard, ScientificClaimAuditResult, audit_grounded_claims
from targetintel.llm.grounded_prompt import build_grounded_extraction_request
from targetintel.llm.grounded_schema import GROUNDED_EXTRACTION_SCHEMA_ID, GROUNDED_EXTRACTION_SCHEMA_VERSION


SOURCE = "B2M may be associated with response in a small cohort of melanoma patients."


def _extraction(claim, source=SOURCE):
    request = build_grounded_extraction_request(request_id="audit-request", source_document_id="audit-doc", source_text=source)
    provenance = ProviderProvenance("audit-request", "mock", "model", None, request.prompt_id, request.prompt_version,
        GROUNDED_EXTRACTION_SCHEMA_ID, GROUNDED_EXTRACTION_SCHEMA_VERSION, request.task_type, "audit-doc", LLMResultStatus.SUCCESS)
    output = {"schema_id": GROUNDED_EXTRACTION_SCHEMA_ID, "schema_version": GROUNDED_EXTRACTION_SCHEMA_VERSION,
              "source_document_id": "audit-doc", "claims": [claim]}
    return extract_grounded_candidates(request, LLMResponse(provenance, structured_output=output))


def _extraction_many(claims, source):
    request = build_grounded_extraction_request(request_id="audit-request", source_document_id="audit-doc", source_text=source)
    provenance = ProviderProvenance("audit-request", "mock", "model", None, request.prompt_id, request.prompt_version,
        GROUNDED_EXTRACTION_SCHEMA_ID, GROUNDED_EXTRACTION_SCHEMA_VERSION, request.task_type, "audit-doc", LLMResultStatus.SUCCESS)
    output = {"schema_id": GROUNDED_EXTRACTION_SCHEMA_ID, "schema_version": GROUNDED_EXTRACTION_SCHEMA_VERSION,
              "source_document_id": "audit-doc", "claims": claims}
    return extract_grounded_candidates(request, LLMResponse(provenance, structured_output=output))


def _claim(text="B2M may be associated with response in a small cohort of melanoma patients.", **extra):
    value = {"claim_text": text, "quoted_span": SOURCE[:-1], "quote_start": 0, "quote_end": len(SOURCE) - 1,
             "stance": "supports", "target_mentions": ["B2M"], "disease_mentions": ["melanoma"]}
    value.update(extra)
    return value


def test_pass_immutable_serialized_card_and_result():
    source = SOURCE + " complete-document-tail-not-in-quote"
    result = audit_grounded_claims(_extraction(_claim(), source), "audit-doc", source)
    assert result.overall_decision == result.cards[0].release_decision == "pass"
    assert result.canonical_json() == audit_grounded_claims(_extraction(_claim(), source), "audit-doc", source).canonical_json()
    assert isinstance(result.cards[0].candidate_provenance, MappingProxyType)
    assert result.cards[0].research_only and result.cards[0].not_clinical_guidance and result.cards[0].not_evidence_item
    with pytest.raises(TypeError): result.cards[0].candidate_provenance["x"] = "x"


def test_lexical_warnings_and_blockers_are_release_gates():
    warning = audit_grounded_claims(_extraction(_claim("B2M causes response and proves benefit.")), "audit-doc", SOURCE)
    assert warning.overall_decision == "review"
    assert {x.rule_id for x in warning.cards[0].findings} >= {"association_presented_as_causation", "certainty_inflation", "missing_source_limitation"}
    blocker = audit_grounded_claims(_extraction(_claim("Patients should receive B2M therapy at a 10 mg dose.")), "audit-doc", SOURCE)
    assert blocker.overall_decision == "block"
    assert {x.rule_id for x in blocker.cards[0].findings} >= {"unsupported_therapeutic_recommendation", "clinical_guidance_language"}


def test_preclinical_identifiers_negation_and_grounding_fail_closed():
    preclinical = audit_grounded_claims(_extraction(_claim("B2M showed clinical efficacy.", model_system_mentions=["mouse"])), "audit-doc", SOURCE)
    assert preclinical.overall_decision == "block"
    unanchored = audit_grounded_claims(_extraction(_claim(target_mentions=["NOT_IN_SOURCE"])), "audit-doc", SOURCE)
    assert unanchored.overall_decision == "block"
    negated = audit_grounded_claims(_extraction(_claim("The study does not support recommending treatment.")), "audit-doc", SOURCE)
    assert "unsupported_therapeutic_recommendation" not in {x.rule_id for x in negated.cards[0].findings}
    mismatch = audit_grounded_claims(_extraction(_claim()), "audit-doc", SOURCE + " ")
    assert mismatch.overall_decision == "block"


def test_invalid_and_empty_extractions_are_not_biological_evidence():
    empty_request = build_grounded_extraction_request(request_id="empty", source_document_id="audit-doc", source_text=SOURCE)
    p = ProviderProvenance("empty", "mock", "model", None, empty_request.prompt_id, empty_request.prompt_version, GROUNDED_EXTRACTION_SCHEMA_ID, GROUNDED_EXTRACTION_SCHEMA_VERSION, empty_request.task_type, "audit-doc", LLMResultStatus.SUCCESS)
    empty = extract_grounded_candidates(empty_request, LLMResponse(p, structured_output={"schema_id": GROUNDED_EXTRACTION_SCHEMA_ID, "schema_version": GROUNDED_EXTRACTION_SCHEMA_VERSION, "source_document_id": "audit-doc", "claims": []}))
    assert audit_grounded_claims(empty, "audit-doc", SOURCE).overall_decision == "no_candidates"
    all_rejected = _extraction_many([{"claim_text": "Rejected", "quoted_span": "not present", "quote_start": 0,
                                      "quote_end": 11, "stance": "supports"}], SOURCE)
    assert not all_rejected.no_claims
    assert not all_rejected.accepted_candidates
    assert audit_grounded_claims(all_rejected, "audit-doc", SOURCE).overall_decision == "no_candidates"
    assert audit_grounded_claims("bad", "audit-doc", SOURCE).overall_decision == "invalid_input"
    with pytest.raises(ValueError): ClaimAuditFinding("unknown", "scientific-claim-audit-v1", "blocker", "x")


def test_within_source_opposed_stances_flag_all_shared_anchor_candidates():
    source = "B2M is associated with response in melanoma."
    quote = source[:-1]
    common = {"quoted_span": quote, "quote_start": 0, "quote_end": len(quote),
              "target_mentions": ["B2M"], "disease_mentions": ["melanoma"]}
    extraction = _extraction_many([
        {"claim_text": "B2M is associated with response in melanoma.", "stance": "supports", **common},
        {"claim_text": "B2M is associated with response in melanoma.", "stance": "contradicts", **common},
    ], source)

    result = audit_grounded_claims(extraction, "audit-doc", source)

    assert len(result.cards) == 2
    assert [card.candidate_id for card in result.cards] == [candidate.candidate_id for candidate in extraction.accepted_candidates]
    assert all(card.release_decision == "review" for card in result.cards)
    assert all("within_source_contradiction" in {finding.rule_id for finding in card.findings} for card in result.cards)
    assert {card.stance for card in result.cards} == {"supports", "contradicts"}


@pytest.mark.parametrize("claim_text", [
    "Patients should receive B2M therapy.", "Clinicians should use B2M.",
    "B2M is the recommended treatment.", "B2M is first-line treatment.",
    "B2M is standard of care.", "Administer B2M.", "Prescribe B2M.",
    "B2M is clinically indicated.", "B2M should be avoided.",
    "B2M is contraindicated.", "B2M is an effective therapy for patients.",
])
def test_therapeutic_recommendation_variants_block(claim_text):
    result = audit_grounded_claims(_extraction(_claim(claim_text)), "audit-doc", SOURCE)
    assert result.cards[0].release_decision == "block"
    assert "unsupported_therapeutic_recommendation" in {x.rule_id for x in result.cards[0].findings}


@pytest.mark.parametrize("claim_text", [
    "The B2M dose is 10 mg.", "B2M dosing is weekly.", "Use intravenous B2M.",
    "Use oral administration of B2M.", "Select patients for B2M.",
    "B2M is second-line after progression.", "Monitor response to B2M.",
    "Diagnose melanoma before B2M.", "Patients must be treated with B2M.",
])
def test_clinical_guidance_variants_block_even_with_negated_recommendation(claim_text):
    result = audit_grounded_claims(_extraction(_claim(
        "The study does not support recommending treatment. " + claim_text)), "audit-doc", SOURCE)
    rules = {x.rule_id for x in result.cards[0].findings}
    assert "unsupported_therapeutic_recommendation" not in rules
    assert "clinical_guidance_language" in rules
    assert result.cards[0].release_decision == "block"


def test_causal_source_wording_does_not_receive_association_warning():
    source = "B2M causes response and is associated with melanoma."
    claim = {"claim_text": "B2M causes response.", "quoted_span": source[:-1],
             "quote_start": 0, "quote_end": len(source) - 1, "stance": "supports",
             "target_mentions": ["B2M"], "disease_mentions": ["melanoma"]}
    result = audit_grounded_claims(_extraction(claim, source), "audit-doc", source)
    assert "association_presented_as_causation" not in {x.rule_id for x in result.cards[0].findings}


@pytest.mark.parametrize("model, claim_text", [
    ("mouse", "B2M demonstrated patient benefit."),
    ("organoid", "B2M showed clinical efficacy."),
    ("cell line", "B2M enables clinical response prediction."),
])
def test_preclinical_clinical_extrapolation_variants_block(model, claim_text):
    result = audit_grounded_claims(_extraction(_claim(claim_text, model_system_mentions=[model])), "audit-doc", SOURCE)
    assert result.cards[0].release_decision == "block"
    assert "preclinical_presented_as_clinical" in {x.rule_id for x in result.cards[0].findings}


def test_preclinical_description_and_missing_metadata_do_not_invent_extrapolation():
    preclinical = audit_grounded_claims(_extraction(_claim("B2M was observed in a mouse model.", model_system_mentions=["mouse"])), "audit-doc", SOURCE)
    absent = audit_grounded_claims(_extraction(_claim("B2M showed clinical efficacy.")), "audit-doc", SOURCE)
    assert "preclinical_presented_as_clinical" not in {x.rule_id for x in preclinical.cards[0].findings}
    assert "preclinical_presented_as_clinical" not in {x.rule_id for x in absent.cards[0].findings}


@pytest.mark.parametrize("claim_text, extra", [
    ("B2M applies to all cancers.", {}),
    ("B2M applies to all patients.", {"cohort_description": "melanoma patients"}),
])
def test_explicit_context_generalization_requires_review(claim_text, extra):
    result = audit_grounded_claims(_extraction(_claim(claim_text, **extra)), "audit-doc", SOURCE)
    assert result.cards[0].release_decision == "review"
    assert "unsupported_population_generalization" in {x.rule_id for x in result.cards[0].findings}


@pytest.mark.parametrize("source, claim_text, expected", [
    ("B2M response had no significant difference in melanoma.", "B2M response was observed in melanoma.", "no significant difference"),
    ("B2M response is preliminary in melanoma.", "B2M response was observed in melanoma.", "preliminary"),
    ("B2M response came from a small cohort of melanoma.", "B2M response was observed in melanoma.", "small cohort"),
])
def test_explicit_source_limitations_omitted_require_review(source, claim_text, expected):
    quote = source[:-1]
    claim = {"claim_text": claim_text, "quoted_span": quote, "quote_start": 0,
             "quote_end": len(quote), "stance": "supports", "target_mentions": ["B2M"],
             "disease_mentions": ["melanoma"]}
    result = audit_grounded_claims(_extraction(claim, source), "audit-doc", source)
    findings = [x for x in result.cards[0].findings if x.rule_id == "missing_source_limitation"]
    assert findings and expected in findings[0].audit_fields["limitation_markers"]
    preserved = audit_grounded_claims(_extraction({**claim, "claim_text": claim_text + " This is " + expected + "."}, source), "audit-doc", source)
    assert "missing_source_limitation" not in {x.rule_id for x in preserved.cards[0].findings}


@pytest.mark.parametrize("field, value", [
    ("target_mentions", ["NOT_IN_SOURCE"]), ("disease_mentions", ["NOT_IN_SOURCE"]),
    ("species_mentions", ["NOT_IN_SOURCE"]), ("model_system_mentions", ["NOT_IN_SOURCE"]),
    ("cohort_description", "NOT_IN_SOURCE"),
])
def test_each_unanchored_identifier_field_blocks(field, value):
    result = audit_grounded_claims(_extraction(_claim(**{field: value})), "audit-doc", SOURCE)
    assert result.cards[0].release_decision == "block"
    assert "invented_or_unanchored_identifier" in {x.rule_id for x in result.cards[0].findings}


@pytest.mark.parametrize("attribute, value", [
    ("source_document_id", "wrong-doc"), ("source_content_hash", "not-a-hash"),
    ("quote_start", -1), ("quote_end", len(SOURCE) + 1), ("quoted_span", "wrong quote"),
])
def test_defensive_grounding_recheck_blocks_directly_modified_candidates(attribute, value):
    extraction = _extraction(_claim())
    bad_candidate = replace(extraction.accepted_candidates[0], **{attribute: value})
    result = audit_grounded_claims(replace(extraction, accepted_candidates=(bad_candidate,)), "audit-doc", SOURCE)
    assert result.cards[0].release_decision == "block"
    assert any(x.rule_id in {"grounding_integrity_failure", "source_identity_mismatch"} for x in result.cards[0].findings)


def test_ambiguous_stance_mixed_findings_and_ordering_are_deterministic():
    ambiguous = audit_grounded_claims(_extraction(_claim(stance="unclear")), "audit-doc", SOURCE)
    assert ambiguous.cards[0].release_decision == "review"
    mixed = audit_grounded_claims(_extraction(_claim("B2M causes response. Patients should receive B2M therapy.")), "audit-doc", SOURCE)
    assert mixed.cards[0].release_decision == "block"
    assert {x.severity for x in mixed.cards[0].findings} >= {"warning", "blocker"}
    repeat = audit_grounded_claims(_extraction(_claim("B2M causes response. Patients should receive B2M therapy.")), "audit-doc", SOURCE)
    assert [x.to_dict() for x in mixed.cards[0].findings] == [x.to_dict() for x in repeat.cards[0].findings]
    assert mixed.audit_result_id == repeat.audit_result_id


def test_audit_public_values_are_immutable_and_distinct_from_evidence_items():
    finding = ClaimAuditFinding("missing_source_limitation", "scientific-claim-audit-v1", "warning", "code", audit_fields={"nested": ["x"]})
    assert isinstance(finding.audit_fields, MappingProxyType)
    with pytest.raises(TypeError): finding.audit_fields["nested"] = ()
    with pytest.raises(TypeError): finding.audit_fields["nested"][0] = "y"
    source = SOURCE + " complete-document-tail-not-in-quote"
    result = audit_grounded_claims(_extraction(_claim(), source), "audit-doc", source)
    assert isinstance(result, ScientificClaimAuditResult)
    assert isinstance(result.cards[0], ClaimBoundaryCard)
    serialized = result.to_dict()
    assert "complete-document-tail-not-in-quote" not in result.cards[0].canonical_json()
    assert "reasoning" not in result.canonical_json().lower()
    assert result.cards[0].card_id == audit_grounded_claims(_extraction(_claim(), source), "audit-doc", source).cards[0].card_id


@pytest.mark.parametrize("marker", [
    "causes", "drives", "determines", "produces", "leads to", "results in", "mediates", "is required for",
])
def test_associative_quotes_do_not_support_each_causal_claim_marker(marker):
    result = audit_grounded_claims(_extraction(_claim("B2M " + marker + " response.")), "audit-doc", SOURCE)
    assert "association_presented_as_causation" in {x.rule_id for x in result.cards[0].findings}


@pytest.mark.parametrize("marker", [
    "proves", "demonstrates conclusively", "establishes", "confirms", "definitively", "clearly shows", "validates",
])
def test_uncertain_quotes_do_not_support_each_strong_certainty_marker(marker):
    source = "B2M may be associated with melanoma."
    quote = source[:-1]
    claim = {"claim_text": "B2M " + marker + " benefit.", "quoted_span": quote,
             "quote_start": 0, "quote_end": len(quote), "stance": "supports",
             "target_mentions": ["B2M"], "disease_mentions": ["melanoma"]}
    result = audit_grounded_claims(_extraction(claim, source), "audit-doc", source)
    assert "certainty_inflation" in {x.rule_id for x in result.cards[0].findings}


@pytest.mark.parametrize("negated", [
    "does not support recommending treatment", "no therapeutic recommendation can be made",
    "not recommend treatment", "cannot recommend treatment",
])
def test_explicit_no_recommendation_boundaries_remain_safe(negated):
    result = audit_grounded_claims(_extraction(_claim("The study " + negated + ".")), "audit-doc", SOURCE)
    # The source's separately omitted small-cohort limitation can still
    # require review; the boundary itself must never become a blocker.
    assert result.cards[0].release_decision != "block"
    assert "unsupported_therapeutic_recommendation" not in {x.rule_id for x in result.cards[0].findings}


def test_negated_boundary_does_not_suppress_separate_therapeutic_recommendation():
    result = audit_grounded_claims(_extraction(_claim(
        "The study does not support recommending treatment. "
        "B2M is standard of care and contraindicated for elderly patients."
    )), "audit-doc", SOURCE)
    rules = {finding.rule_id for finding in result.cards[0].findings}
    assert "unsupported_therapeutic_recommendation" in rules
    assert result.cards[0].release_decision == "block"


@pytest.mark.parametrize("limitation", [
    "limited sample size", "exploratory", "retrospective", "single cohort",
    "requires validation", "not statistically significant", "uncertain", "inconclusive",
])
def test_additional_explicit_limitations_are_preserved_or_flagged(limitation):
    source = "B2M is associated with melanoma; this is " + limitation + "."
    quote = source[:-1]
    base = {"quoted_span": quote, "quote_start": 0, "quote_end": len(quote),
            "stance": "supports", "target_mentions": ["B2M"], "disease_mentions": ["melanoma"]}
    omitted = audit_grounded_claims(_extraction({**base, "claim_text": "B2M is associated with melanoma."}, source), "audit-doc", source)
    preserved = audit_grounded_claims(_extraction({**base, "claim_text": "B2M is associated with melanoma; this is " + limitation + "."}, source), "audit-doc", source)
    assert "missing_source_limitation" in {x.rule_id for x in omitted.cards[0].findings}
    assert "missing_source_limitation" not in {x.rule_id for x in preserved.cards[0].findings}


@pytest.mark.parametrize("field, value", [
    ("target_mentions", ["B2M"]), ("disease_mentions", ["melanoma"]),
    ("species_mentions", ["human"]), ("model_system_mentions", ["patient"]),
    ("cohort_description", "melanoma patients"),
])
def test_exactly_anchored_identifier_fields_are_accepted(field, value):
    source = SOURCE + " human patient"
    result = audit_grounded_claims(_extraction(_claim(**{field: value}), source), "audit-doc", source)
    assert "invented_or_unanchored_identifier" not in {x.rule_id for x in result.cards[0].findings}


def test_failed_extraction_and_missing_candidate_identity_fail_closed():
    extraction = _extraction(_claim())
    failed = audit_grounded_claims(replace(extraction, status=GroundedExtractionStatus.FAILED), "audit-doc", SOURCE)
    assert failed.overall_decision == "invalid_input"
    missing_id = replace(extraction.accepted_candidates[0], candidate_id="")
    audited = audit_grounded_claims(replace(extraction, accepted_candidates=(missing_id,)), "audit-doc", SOURCE)
    assert audited.cards[0].release_decision == "block"
    assert "candidate_not_audited" in {x.rule_id for x in audited.cards[0].findings}


def test_contradictions_require_complete_shared_anchors_and_preserve_candidates():
    source = "B2M is associated with response in melanoma."
    quote = source[:-1]
    one = {"claim_text": "B2M is associated with response in melanoma.", "quoted_span": quote,
           "quote_start": 0, "quote_end": len(quote), "target_mentions": ["B2M"],
           "disease_mentions": ["melanoma"]}
    extraction = _extraction_many([{**one, "stance": "supports"}, {**one, "stance": "contradicts", "disease_mentions": []}], source)
    result = audit_grounded_claims(extraction, "audit-doc", source)
    assert len(result.cards) == 2
    assert all("within_source_contradiction" not in {x.rule_id for x in card.findings} for card in result.cards)

"""Pure, deterministic scientific wording audit for grounded staging claims."""
from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import sha256
import re
from types import MappingProxyType
from typing import Any, Mapping

from .claim_rules import (ASSOCIATIVE_MARKERS, CAUSAL_MARKERS, CLAIM_AUDIT_TAXONOMY_VERSION,
    CLINICAL_EXTRAPOLATION_MARKERS, CLINICAL_GUIDANCE_MARKERS, LIMITATION_MARKERS,
    NEGATED_RECOMMENDATION_MARKERS, PRECLINICAL_MARKERS, STRONG_CERTAINTY_MARKERS,
    THERAPEUTIC_RECOMMENDATION_MARKERS, UNCERTAINTY_MARKERS, severity_for_rule, taxonomy_dict)
from .contracts import _freeze, _thaw, canonical_json
from .grounded_extraction import GroundedClaimCandidate, GroundedExtractionResult, GroundedExtractionStatus


CLAIM_AUDIT_FORMAT_VERSION = "scientific-claim-audit-result-v1"
CLAIM_BOUNDARY_CARD_FORMAT_VERSION = "claim-boundary-card-v1"
_DECISIONS = frozenset({"pass", "review", "block"})


def _text_markers(text: str, markers: tuple[str, ...]) -> tuple[str, ...]:
    lower = text.lower()
    return tuple(marker for marker in markers if marker in lower)


def _unnegated_therapeutic_markers(claim_text: str) -> tuple[str, ...]:
    """Return recommendation markers outside a locally negated sentence/clause.

    This intentionally limited lexical handling treats only a sentence or
    semicolon-delimited clause containing an explicit boundary marker as
    negated.  A boundary statement elsewhere in the claim must not suppress a
    separate positive therapeutic recommendation.
    """
    markers: list[str] = []
    for clause in re.split(r"[.!?;]+", claim_text):
        if _text_markers(clause, NEGATED_RECOMMENDATION_MARKERS):
            continue
        markers.extend(_text_markers(clause, THERAPEUTIC_RECOMMENDATION_MARKERS))
    return tuple(markers)


@dataclass(frozen=True)
class ClaimAuditFinding:
    rule_id: str
    taxonomy_version: str
    severity: str
    message_code: str
    candidate_id: str | None = None
    explanation: str = ""
    audit_fields: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.taxonomy_version != CLAIM_AUDIT_TAXONOMY_VERSION:
            raise ValueError("unknown claim-audit taxonomy version")
        if self.severity != severity_for_rule(self.rule_id):
            raise ValueError("claim-audit severity must match the built-in rule")
        if not self.message_code or not isinstance(self.message_code, str):
            raise ValueError("message_code must be non-empty")
        if not isinstance(self.explanation, str):
            raise ValueError("explanation must be a string")
        object.__setattr__(self, "audit_fields", _freeze(self.audit_fields))

    def to_dict(self) -> dict[str, Any]:
        return {"rule_id": self.rule_id, "taxonomy_version": self.taxonomy_version,
                "severity": self.severity, "message_code": self.message_code,
                "candidate_id": self.candidate_id, "explanation": self.explanation,
                "audit_fields": _thaw(self.audit_fields)}

    def canonical_json(self) -> str: return canonical_json(self.to_dict())


def _finding(rule: str, candidate_id: str | None, code: str, explanation: str, **fields: Any) -> ClaimAuditFinding:
    return ClaimAuditFinding(rule, CLAIM_AUDIT_TAXONOMY_VERSION, severity_for_rule(rule), code, candidate_id, explanation, fields)


@dataclass(frozen=True)
class ClaimBoundaryCard:
    card_format_version: str
    card_id: str
    candidate_id: str
    source_document_id: str
    source_content_hash: str
    claim_text: str
    quoted_span: str
    quote_start: int
    quote_end: int
    stance: str
    candidate_provenance: Mapping[str, Any]
    findings: tuple[ClaimAuditFinding, ...]
    release_decision: str
    claim_origin: str = "grounded_llm_extraction"
    research_only: bool = True
    not_clinical_guidance: bool = True
    not_evidence_item: bool = True
    human_review_required_before_promotion: bool = True

    def __post_init__(self) -> None:
        if self.release_decision not in _DECISIONS: raise ValueError("invalid release decision")
        if not all(isinstance(item, ClaimAuditFinding) for item in self.findings): raise ValueError("findings must be audit findings")
        object.__setattr__(self, "candidate_provenance", _freeze(self.candidate_provenance))

    def to_dict(self) -> dict[str, Any]:
        return {"card_format_version": self.card_format_version, "card_id": self.card_id,
                "candidate_id": self.candidate_id, "source_document_id": self.source_document_id,
                "source_content_hash": self.source_content_hash, "claim_text": self.claim_text,
                "quoted_span": self.quoted_span, "quote_start": self.quote_start, "quote_end": self.quote_end,
                "stance": self.stance, "candidate_provenance": _thaw(self.candidate_provenance),
                "findings": [item.to_dict() for item in self.findings], "release_decision": self.release_decision,
                "claim_origin": self.claim_origin, "research_only": self.research_only,
                "not_clinical_guidance": self.not_clinical_guidance, "not_evidence_item": self.not_evidence_item,
                "human_review_required_before_promotion": self.human_review_required_before_promotion}
    def canonical_json(self) -> str: return canonical_json(self.to_dict())


@dataclass(frozen=True)
class ScientificClaimAuditResult:
    audit_format_version: str
    audit_taxonomy_version: str
    source_document_id: str
    source_content_hash: str
    extraction_result_id: str
    cards: tuple[ClaimBoundaryCard, ...]
    cross_candidate_findings: tuple[ClaimAuditFinding, ...]
    accepted_candidate_count: int
    pass_count: int
    review_count: int
    block_count: int
    overall_decision: str
    audit_result_id: str

    def __post_init__(self) -> None:
        if self.overall_decision not in {"pass", "review", "block", "invalid_input", "no_candidates"}: raise ValueError("invalid overall decision")
        object.__setattr__(self, "cards", tuple(self.cards)); object.__setattr__(self, "cross_candidate_findings", tuple(self.cross_candidate_findings))
    def to_dict(self) -> dict[str, Any]:
        return {"audit_format_version": self.audit_format_version, "audit_taxonomy_version": self.audit_taxonomy_version,
                "source_document_id": self.source_document_id, "source_content_hash": self.source_content_hash,
                "extraction_result_id": self.extraction_result_id, "cards": [x.to_dict() for x in self.cards],
                "cross_candidate_findings": [x.to_dict() for x in self.cross_candidate_findings],
                "accepted_candidate_count": self.accepted_candidate_count, "pass_count": self.pass_count,
                "review_count": self.review_count, "block_count": self.block_count, "overall_decision": self.overall_decision,
                "audit_result_id": self.audit_result_id}
    def canonical_json(self) -> str: return canonical_json(self.to_dict())


def _decision(findings: tuple[ClaimAuditFinding, ...]) -> str:
    return "block" if any(x.severity == "blocker" for x in findings) else "review" if any(x.severity == "warning" for x in findings) else "pass"

def _card(candidate: GroundedClaimCandidate, findings: tuple[ClaimAuditFinding, ...]) -> ClaimBoundaryCard:
    decision = _decision(findings)
    provenance = {"request_identity": candidate.request_identity, "response_identity": candidate.response_identity,
                  "prompt_id": candidate.prompt_id, "prompt_version": candidate.prompt_version,
                  "schema_id": candidate.schema_id, "schema_version": candidate.schema_version,
                  "claim_origin": "grounded_llm_extraction", "audit_origin": "deterministic_audit"}
    identity = {"card_format_version": CLAIM_BOUNDARY_CARD_FORMAT_VERSION, "taxonomy_version": CLAIM_AUDIT_TAXONOMY_VERSION,
                "candidate_id": candidate.candidate_id, "findings": [x.to_dict() for x in findings], "release_decision": decision,
                "research_only": True, "not_clinical_guidance": True, "not_evidence_item": True}
    card_id = sha256(canonical_json(identity).encode("utf-8")).hexdigest()
    return ClaimBoundaryCard(CLAIM_BOUNDARY_CARD_FORMAT_VERSION, card_id, candidate.candidate_id, candidate.source_document_id,
        candidate.source_content_hash, candidate.claim_text, candidate.quoted_span, candidate.quote_start, candidate.quote_end,
        candidate.stance, provenance, findings, decision)

def _candidate_findings(candidate: GroundedClaimCandidate, source_document_id: str, source: str, source_hash: str) -> list[ClaimAuditFinding]:
    found: list[ClaimAuditFinding] = []
    if not isinstance(candidate.candidate_id, str) or not candidate.candidate_id:
        found.append(_finding("candidate_not_audited", None, "candidate_identity_missing", "Candidate cannot be released because its deterministic identity is missing."))
    if candidate.source_document_id != source_document_id or candidate.source_content_hash != source_hash:
        found.append(_finding("source_identity_mismatch", candidate.candidate_id, "source_identity_mismatch", "Candidate source identity does not match the supplied audit source."))
    valid_offsets = (isinstance(candidate.quote_start, int) and not isinstance(candidate.quote_start, bool) and isinstance(candidate.quote_end, int) and not isinstance(candidate.quote_end, bool) and 0 <= candidate.quote_start < candidate.quote_end <= len(source))
    if not valid_offsets or (valid_offsets and source[candidate.quote_start:candidate.quote_end] != candidate.quoted_span):
        found.append(_finding("grounding_integrity_failure", candidate.candidate_id, "exact_quote_mismatch", "Candidate quote grounding does not exactly match the supplied source."))
    claim, quote = candidate.claim_text, candidate.quoted_span
    therapeutic = _unnegated_therapeutic_markers(claim)
    if therapeutic: found.append(_finding("unsupported_therapeutic_recommendation", candidate.candidate_id, "therapeutic_recommendation_language", "Claim contains therapeutic recommendation wording.", markers=therapeutic))
    # Recommendation-negation handling is deliberately limited to the
    # therapeutic-recommendation rule.  Clinical guidance is independently
    # unsafe public wording even where a separate sentence rejects treatment.
    guidance = _text_markers(claim, CLINICAL_GUIDANCE_MARKERS)
    if guidance: found.append(_finding("clinical_guidance_language", candidate.candidate_id, "clinical_guidance_language", "Claim contains patient-level clinical guidance wording.", markers=guidance))
    causal, assoc = _text_markers(claim, CAUSAL_MARKERS), _text_markers(quote, ASSOCIATIVE_MARKERS)
    quote_causal = _text_markers(quote, CAUSAL_MARKERS)
    # This lexical rule applies only when the quote is exclusively
    # associative/observational; a quote with explicit causal wording is not
    # downgraded merely because it also contains an associative marker.
    if causal and assoc and not quote_causal: found.append(_finding("association_presented_as_causation", candidate.candidate_id, "causal_claim_over_associative_quote", "Claim uses causal wording while the quote uses associative wording.", claim_markers=causal, quote_markers=assoc))
    strong, uncertain = _text_markers(claim, STRONG_CERTAINTY_MARKERS), _text_markers(quote, UNCERTAINTY_MARKERS)
    if strong and uncertain: found.append(_finding("certainty_inflation", candidate.candidate_id, "certainty_exceeds_quote", "Claim certainty exceeds uncertainty explicitly present in the quote.", claim_markers=strong, quote_markers=uncertain))
    raw_text = " ".join(str(v) if isinstance(v, str) else " ".join(v) for v in candidate.raw_fields.values())
    models = _text_markers(raw_text, PRECLINICAL_MARKERS)
    clinical = _text_markers(claim, CLINICAL_EXTRAPOLATION_MARKERS)
    if models and clinical: found.append(_finding("preclinical_presented_as_clinical", candidate.candidate_id, "preclinical_clinical_extrapolation", "Explicit preclinical metadata is presented as clinical benefit or efficacy.", model_markers=models, clinical_markers=clinical))
    disease_mentions = tuple(candidate.raw_fields.get("disease_mentions", ()))
    cohort = candidate.raw_fields.get("cohort_description", "")
    broader = _text_markers(claim, ("all cancers", "all patients", "every patient", "all tumors"))
    narrower = tuple(item for item in disease_mentions if isinstance(item, str) and item and item.lower() not in claim.lower())
    if broader and (disease_mentions or cohort):
        found.append(_finding("unsupported_population_generalization", candidate.candidate_id, "claim_broader_than_explicit_context", "Claim generalizes beyond explicit disease or cohort context supplied for the candidate.", broad_markers=broader, disease_mentions=disease_mentions, has_cohort_description=bool(cohort)))
    limits = _text_markers(quote + " " + raw_text, LIMITATION_MARKERS)
    if limits and not _text_markers(claim, limits): found.append(_finding("missing_source_limitation", candidate.candidate_id, "source_limitation_omitted", "An explicit source limitation is absent from the extracted claim.", limitation_markers=limits))
    for key in ("target_mentions", "disease_mentions", "species_mentions", "model_system_mentions", "cohort_description"):
        value = candidate.raw_fields.get(key)
        values = value if isinstance(value, tuple) else (() if value in (None, "") else (value,))
        for item in values:
            if isinstance(item, str) and item and item not in source and item not in quote:
                found.append(_finding("invented_or_unanchored_identifier", candidate.candidate_id, "unanchored_identifier", "Extracted identifier is not exactly anchored in the source or quote.", field=key, identifier=item))
    if candidate.stance in {"unclear", "contextual"}:
        found.append(_finding("ambiguous_support_relation", candidate.candidate_id, "ambiguous_stance", "Candidate stance requires human interpretation review.", stance=candidate.stance))
    return found

def audit_grounded_claims(extraction_result: GroundedExtractionResult, source_document_id: str, source_text: str) -> ScientificClaimAuditResult:
    """Audit Issue 304 candidates without invoking providers, I/O, or external knowledge."""
    source_hash = sha256(source_text.encode("utf-8")).hexdigest() if isinstance(source_text, str) else ""
    invalid = not isinstance(extraction_result, GroundedExtractionResult) or not isinstance(source_document_id, str) or not source_document_id or not isinstance(source_text, str)
    candidates = () if invalid else extraction_result.accepted_candidates
    cross: list[ClaimAuditFinding] = []
    cards: list[ClaimBoundaryCard] = []
    extraction_invalid = invalid or extraction_result.status is not GroundedExtractionStatus.SUCCESS or not extraction_result.result_id
    result_hash_mismatch = not invalid and extraction_result.source_content_hash != source_hash
    if extraction_invalid:
        cross.append(_finding("audit_input_invalid", None, "invalid_extraction_input", "Extraction result is not a successful auditable staging result."))
    if result_hash_mismatch:
        cross.append(_finding("source_identity_mismatch", None, "extraction_source_hash_mismatch", "Extraction source hash does not match the supplied audit source."))
    if not invalid and candidates:
        for candidate in candidates:
            individual = _candidate_findings(candidate, source_document_id, source_text, source_hash)
            if extraction_invalid:
                individual.append(_finding("audit_input_invalid", candidate.candidate_id, "invalid_extraction_input", "Candidate cannot pass because its extraction result is invalid."))
            if result_hash_mismatch:
                individual.append(_finding("source_identity_mismatch", candidate.candidate_id, "extraction_source_hash_mismatch", "Candidate cannot pass because extraction source hash does not match the audit source."))
            findings = tuple(individual)
            cards.append(_card(candidate, findings))
        # Explicit contradiction only with identical non-empty target and disease anchors.
        for i, left in enumerate(candidates):
            for right in candidates[i + 1:]:
                lt, rt = tuple(left.raw_fields.get("target_mentions", ())), tuple(right.raw_fields.get("target_mentions", ()))
                ld, rd = tuple(left.raw_fields.get("disease_mentions", ())), tuple(right.raw_fields.get("disease_mentions", ()))
                if lt and ld and tuple(x.lower() for x in lt) == tuple(x.lower() for x in rt) and tuple(x.lower() for x in ld) == tuple(x.lower() for x in rd) and {left.stance, right.stance} == {"supports", "contradicts"}:
                    for candidate in (left, right):
                        idx = next(j for j, card in enumerate(cards) if card.candidate_id == candidate.candidate_id)
                        updated = tuple(list(cards[idx].findings) + [_finding("within_source_contradiction", candidate.candidate_id, "opposed_stances_shared_anchors", "Another candidate in this extraction has the opposite stance with the same explicit anchors.", other_candidate_id=right.candidate_id if candidate is left else left.candidate_id)])
                        cards[idx] = _card(candidate, updated)
    passes, reviews, blocks = (sum(card.release_decision == x for card in cards) for x in ("pass", "review", "block"))
    # A successful parser result may contain only rejected proposed claims.
    # It has no auditable candidates regardless of the parser's ``no_claims``
    # flag, so it must never become a passing audit release decision.
    overall = "invalid_input" if extraction_invalid else "block" if blocks else "review" if reviews else "no_candidates" if not cards else "pass"
    payload = {"audit_format_version": CLAIM_AUDIT_FORMAT_VERSION, "taxonomy_version": CLAIM_AUDIT_TAXONOMY_VERSION, "source_document_id": source_document_id, "source_content_hash": source_hash, "extraction_result_id": "" if invalid else extraction_result.result_id, "cards": [x.to_dict() for x in cards], "cross_candidate_findings": [x.to_dict() for x in cross], "overall_decision": overall}
    return ScientificClaimAuditResult(CLAIM_AUDIT_FORMAT_VERSION, CLAIM_AUDIT_TAXONOMY_VERSION, source_document_id, source_hash, "" if invalid else extraction_result.result_id, tuple(cards), tuple(cross), len(candidates), passes, reviews, blocks, overall, sha256(canonical_json(payload).encode("utf-8")).hexdigest())

# Clear alias for callers that use "scientific claim audit" terminology.
audit_scientific_claims = audit_grounded_claims

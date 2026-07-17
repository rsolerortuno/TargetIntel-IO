"""Versioned, lexical rules used by the deterministic claim critic.

These rules are deliberately small and transparent.  They are wording checks,
not a substitute for scientific, clinical, or citation review.
"""
from __future__ import annotations

from types import MappingProxyType
from typing import Mapping


CLAIM_AUDIT_TAXONOMY_VERSION = "scientific-claim-audit-v1"
SEVERITIES = frozenset({"info", "warning", "blocker"})

# The mapping is public but cannot be mutated by callers.  New rules require a
# taxonomy version change, keeping historical cards interpretable.
RULE_SEVERITIES: Mapping[str, str] = MappingProxyType({
    "grounding_integrity_failure": "blocker",
    "source_identity_mismatch": "blocker",
    "unsupported_therapeutic_recommendation": "blocker",
    "clinical_guidance_language": "blocker",
    "association_presented_as_causation": "warning",
    "certainty_inflation": "warning",
    "preclinical_presented_as_clinical": "blocker",
    "unsupported_population_generalization": "warning",
    "missing_source_limitation": "warning",
    "invented_or_unanchored_identifier": "blocker",
    "ambiguous_support_relation": "warning",
    "within_source_contradiction": "warning",
    "candidate_not_audited": "blocker",
    "audit_input_invalid": "blocker",
})

CAUSAL_MARKERS = ("causes", "drives", "determines", "produces", "is responsible for", "leads to", "results in", "mediates", "is required for")
ASSOCIATIVE_MARKERS = ("associated with", "correlated with", "linked to", "enriched in", "observed in", "higher in", "lower in", "related to")
STRONG_CERTAINTY_MARKERS = ("proves", "demonstrates conclusively", "establishes", "confirms", "definitively", "clearly shows", "validates")
UNCERTAINTY_MARKERS = ("may", "might", "could", "suggests", "possibly", "potentially", "appears", "consistent with", "exploratory", "hypothesis", "preliminary")
LIMITATION_MARKERS = ("small cohort", "limited sample size", "preliminary", "exploratory", "retrospective", "single cohort", "requires validation", "not statistically significant", "no significant difference", "uncertain", "inconclusive", "limitation")
PRECLINICAL_MARKERS = ("mouse", "murine", "rat", "zebrafish", "organoid", "cell line", "in vitro", "ex vivo", "xenograft", "syngeneic model", "animal model", "non-human model")
CLINICAL_EXTRAPOLATION_MARKERS = ("demonstrated patient benefit", "clinical efficacy", "improved survival in patients", "treatment effectiveness in patients", "clinical response prediction", "standard-of-care relevance")
THERAPEUTIC_RECOMMENDATION_MARKERS = ("patients should receive", "clinicians should use", "should be treated with", "recommended treatment", "first-line treatment", "standard of care", "administer", "prescribe", "clinically indicated", "should be avoided", "contraindicated", "effective therapy for patients")
CLINICAL_GUIDANCE_MARKERS = (" mg", "dose", "dosing", "intravenous", "oral administration", "administer", "prescribe", "select patients", "patient selection", "first-line", "second-line", "after progression", "monitor response", "diagnose", "must be treated")
NEGATED_RECOMMENDATION_MARKERS = ("does not support recommending", "no therapeutic recommendation can be made", "not recommend treatment", "cannot recommend treatment")


def severity_for_rule(rule_id: str) -> str:
    """Return the built-in severity, failing closed for unknown rules."""
    if rule_id not in RULE_SEVERITIES:
        raise ValueError("unknown claim-audit rule")
    severity = RULE_SEVERITIES[rule_id]
    if severity not in SEVERITIES:
        raise ValueError("invalid claim-audit severity")
    return severity


def taxonomy_dict() -> dict[str, object]:
    return {"taxonomy_version": CLAIM_AUDIT_TAXONOMY_VERSION,
            "rule_severities": dict(sorted(RULE_SEVERITIES.items()))}

from types import MappingProxyType

import pytest

from targetintel.llm.claim_rules import CLAIM_AUDIT_TAXONOMY_VERSION, RULE_SEVERITIES, SEVERITIES, severity_for_rule, taxonomy_dict


def test_taxonomy_is_stable_immutable_and_fails_closed():
    assert CLAIM_AUDIT_TAXONOMY_VERSION == "scientific-claim-audit-v1"
    assert isinstance(RULE_SEVERITIES, MappingProxyType)
    assert severity_for_rule("grounding_integrity_failure") == "blocker"
    with pytest.raises(TypeError): RULE_SEVERITIES["x"] = "info"
    with pytest.raises(ValueError): severity_for_rule("unknown")
    assert taxonomy_dict() == taxonomy_dict()


def test_taxonomy_contains_the_stable_issue_305_rule_set_and_controlled_severities():
    assert set(RULE_SEVERITIES) == {
        "grounding_integrity_failure", "source_identity_mismatch",
        "unsupported_therapeutic_recommendation", "clinical_guidance_language",
        "association_presented_as_causation", "certainty_inflation",
        "preclinical_presented_as_clinical", "unsupported_population_generalization",
        "missing_source_limitation", "invented_or_unanchored_identifier",
        "ambiguous_support_relation", "within_source_contradiction",
        "candidate_not_audited", "audit_input_invalid",
    }
    assert SEVERITIES == frozenset({"info", "warning", "blocker"})
    assert all(severity in SEVERITIES for severity in RULE_SEVERITIES.values())

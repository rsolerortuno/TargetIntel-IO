"""Offline profile construction regression coverage for Issue 403."""
from dataclasses import FrozenInstanceError, replace

import pytest

from targetintel.feasibility import TargetFeasibilityRequest, build_target_feasibility_profile, build_target_feasibility_profiles
from targetintel.feasibility.models import REQUEST_SCHEMA_ID, REQUEST_SCHEMA_VERSION
from targetintel.feasibility.opentargets_ingestion import fetch_opentargets
from targetintel.feasibility.opentargets_models import (
    OpenTargetsFetchRequest,
    OpenTargetsTargetResolution,
    OpenTargetsTransportResponse,
)
from targetintel.feasibility.opentargets_normalization import OpenTargetsNormalizationManifest
from targetintel.feasibility.opentargets_transport import FakeOpenTargetsTransport


def request(symbol="BRAF"):
    return TargetFeasibilityRequest(REQUEST_SCHEMA_ID, REQUEST_SCHEMA_VERSION, symbol, "gene_symbol", "MONDO:0005105",
        ("clinical_precedence", "tractability", "doability", "safety"), ("antibody", "small_molecule", "protac", "other_clinical"),
        "Open Targets", "24.06", "issue-403")


def result(symbol="BRAF", fields=None, release="24.06"):
    ensembl = "ENSG00000157764"
    target = {"id": ensembl, "approvedSymbol": symbol, **(fields or {})}
    source = OpenTargetsFetchRequest(query_type="directed_target_universe", target_universe=[symbol], requested_source_release=release)
    return fetch_opentargets(source, FakeOpenTargetsTransport({
        "resolve_" + symbol: OpenTargetsTransportResponse("resolve_" + symbol, 200, {"data": {"search": {"hits": [{"id": ensembl, "entity": "TARGET"}]}}}, source_release=release),
        "target_candidate_" + symbol + "_" + ensembl: OpenTargetsTransportResponse("target_candidate_" + symbol + "_" + ensembl, 200, {"data": {"target": target}}, source_release=release),
    }))


def test_manifest_is_immutable_and_identity_is_release_bound():
    first = OpenTargetsNormalizationManifest(source_release="24.06")
    assert first.normalization_schema_id == "targetintel.opentargets-feasibility-normalization"
    assert first.normalization_schema_version == "v0.4.0"
    assert first.normalization_id != OpenTargetsNormalizationManifest(source_release="24.07").normalization_id
    with pytest.raises(FrozenInstanceError): first.source_release = "x"


def test_profile_normalizes_explicit_records_and_preserves_missingness():
    fetched = result(fields={"knownDrugs": {"rows": [{"drug": {"id": "CHEMBL:1", "name": "example"}, "phase": 3, "status": "Approved"}]},
        "tractability": [{"label": "High-quality ligand", "modality": "SMALL MOLECULE", "value": True}, {"label": "No source", "modality": "PROTAC", "value": False}],
        "safetyLiabilities": []})
    built = build_target_feasibility_profile(request(), fetched)
    assert built.status == "built_with_gaps"
    assert built.profile is not None and built.profile.no_score_calculated
    assert {item.dimension for item in built.profile.observations} == {"clinical_precedence", "tractability", "doability", "safety"}
    precedence = next(item for item in built.profile.observations if item.dimension == "clinical_precedence")
    assert precedence.normalized_value["phase"] == 3
    assert any(item.modality == "protac" and item.normalized_value["value"] is False for item in built.profile.observations)
    safety = next(item for item in built.profile.observations if item.dimension == "safety")
    assert safety.availability_state == "not_observed" and safety.normalized_value is None
    assert { (item.dimension, item.modality) for item in built.dimension_coverage } >= {("doability", None), ("tractability", "protac")}


def test_missing_data_is_explicitly_unavailable_and_coverage_is_dimension_scoped():
    fetched = result(fields={"tractability": [{"label": "Unknown", "modality": "UNMAPPED", "value": True}]})
    built = build_target_feasibility_profile(request(), fetched)
    coverage = {(item.dimension, item.modality): item for item in built.dimension_coverage}
    assert coverage[("doability", None)].coverage_state == "not_available"
    assert coverage[("doability", None)].limitations == ("doability_not_retained_by_source_record_contract",)
    assert coverage[("safety", None)].coverage_state == "not_available"
    assert coverage[("safety", None)].unsupported_source_field_count == 0
    assert coverage[("safety", None)].limitations == ("safety_source_field_not_retained",)
    assert coverage[("tractability", None)].unsupported_source_field_count == 1
    assert coverage[("tractability", None)].limitations == ("unsupported_tractability_modality",)
    assert coverage[("tractability", "protac")].coverage_state == "not_available"


def test_exact_matching_and_terminal_outcomes_are_fail_closed():
    fetched = result(fields={"safetyLiabilities": []})
    unresolved = build_target_feasibility_profile(request("NRAS"), fetched)
    assert unresolved.status == "invalid_fetch_result"
    assert unresolved.profile is None


@pytest.mark.parametrize(
    ("resolution_status", "expected_status"),
    [
        ("unresolved", "target_unresolved"),
        ("ambiguous", "target_ambiguous"),
        ("invalid_identifier", "target_invalid"),
        ("retrieval_failed", "target_retrieval_failed"),
    ],
)
def test_explicit_terminal_resolution_statuses_remain_fail_closed(resolution_status, expected_status):
    fetched = result(fields={"safetyLiabilities": []})
    candidates = ({"id": "ENSG00000157764"},) if resolution_status == "ambiguous" else ()
    resolution = OpenTargetsTargetResolution("BRAF", "gene_symbol", resolution_status,
        candidates=candidates, source_release="24.06")
    built = build_target_feasibility_profile(request(), replace(fetched, resolutions=(resolution,)))
    assert built.status == expected_status
    assert built.profile is None
    assert built.error_codes == (expected_status,)
    if expected_status == "target_retrieval_failed":
        assert all(item.coverage_state == "retrieval_failed" for item in built.dimension_coverage)


def test_contradictory_tractability_facts_are_reflected_in_modality_coverage():
    fetched = result(fields={"tractability": [
        {"label": "High-quality ligand", "modality": "SMALL MOLECULE", "value": True},
        {"label": "High-quality ligand", "modality": "SMALL MOLECULE", "value": False},
    ], "safetyLiabilities": []})
    built = build_target_feasibility_profile(request(), fetched)
    coverage = {(item.dimension, item.modality): item for item in built.dimension_coverage}
    overall = coverage[("tractability", None)]
    small_molecule = coverage[("tractability", "small_molecule")]
    assert built.profile is not None and built.profile.contradiction_indicators["has_contradictions"]
    assert overall.coverage_state == small_molecule.coverage_state == "conflicting"
    assert overall.conflicting_count == small_molecule.conflicting_count == 2
    assert len(built.profile.contradiction_indicators["observation_ids"]) == 2


def test_build_result_and_coverage_are_immutable_and_deterministically_serialized():
    built = build_target_feasibility_profile(request(), result(fields={"safetyLiabilities": []}))
    assert built.to_dict() == build_target_feasibility_profile(request(), result(fields={"safetyLiabilities": []})).to_dict()
    assert built.result_id == build_target_feasibility_profile(request(), result(fields={"safetyLiabilities": []})).result_id
    coverage = built.dimension_coverage[0]
    assert coverage.to_dict()["coverage_id"] == coverage.coverage_id
    assert coverage.coverage_is_scientific_confidence is False
    with pytest.raises(FrozenInstanceError):
        built.status = "built"
    with pytest.raises(FrozenInstanceError):
        coverage.coverage_state = "observed"


def test_request_and_fetch_result_are_not_mutated_and_unsupported_records_fail_closed():
    fetched = result(fields={"safetyLiabilities": []})
    request_before, fetch_before = request().to_dict(), fetched.result_id
    build_target_feasibility_profile(request(), fetched)
    assert request().to_dict() == request_before
    assert fetched.result_id == fetch_before
    unsupported_record = replace(fetched.records[0], record_format_version="v2")
    failed = build_target_feasibility_profile(request(), replace(fetched, records=(unsupported_record,)))
    assert failed.status == "normalization_failed"
    assert failed.profile is None


def test_ensembl_request_uses_the_explicit_resolution_identity_without_substitution():
    fetched = result(fields={"safetyLiabilities": []})
    ensembl_request = TargetFeasibilityRequest(REQUEST_SCHEMA_ID, REQUEST_SCHEMA_VERSION,
        "ENSG00000157764", "ensembl_gene_id", "MONDO:0005105", ("safety",), (),
        "Open Targets", "24.06", "issue-403")
    resolution = OpenTargetsTargetResolution("ENSG00000157764", "ensembl_gene_id", "resolved_exact",
        ensembl_gene_id="ENSG00000157764", source_release="24.06")
    built = build_target_feasibility_profile(ensembl_request, replace(fetched, resolutions=(resolution,)))
    assert built.profile is not None
    assert built.target_resolution_id == resolution.resolution_id
    assert built.profile.target_identifier == "ENSG00000157764"


def test_ensembl_request_rejects_a_divergent_resolved_identifier():
    fetched = result(fields={"safetyLiabilities": []})
    ensembl_request = TargetFeasibilityRequest(REQUEST_SCHEMA_ID, REQUEST_SCHEMA_VERSION,
        "ENSG00000157764", "ensembl_gene_id", "MONDO:0005105", ("safety",), (),
        "Open Targets", "24.06", "issue-403")
    divergent_resolution = OpenTargetsTargetResolution("ENSG00000157764", "ensembl_gene_id", "resolved_exact",
        ensembl_gene_id="ENSG00000139618", source_release="24.06")
    built = build_target_feasibility_profile(ensembl_request, replace(fetched, resolutions=(divergent_resolution,)))
    assert built.status == "target_invalid"
    assert built.profile is None
    assert built.error_codes == ("ensembl_resolution_mismatch",)


def test_source_array_order_does_not_alter_clinical_or_safety_profile_identity():
    fields = {"knownDrugs": {"rows": [
        {"drug": {"id": "CHEMBL:2", "name": "two"}, "phase": 2},
        {"drug": {"id": "CHEMBL:1", "name": "one"}, "phase": 3},
    ]}, "safetyLiabilities": [
        {"id": "safety:2", "event": "event two", "effects": ["effect two"]},
        {"id": "safety:1", "event": "event one", "effects": ["effect one"]},
    ]}
    reordered = {"knownDrugs": {"rows": list(reversed(fields["knownDrugs"]["rows"]))},
                 "safetyLiabilities": list(reversed(fields["safetyLiabilities"]))}
    first = build_target_feasibility_profile(request(), result(fields=fields))
    second = build_target_feasibility_profile(request(), result(fields=reordered))
    assert first.profile is not None and second.profile is not None
    assert first.profile.profile_id == second.profile.profile_id


def test_batch_is_order_independent_and_duplicate_request_ids_fail_closed():
    fetched = result(fields={"safetyLiabilities": []})
    one = request(); two = TargetFeasibilityRequest(REQUEST_SCHEMA_ID, REQUEST_SCHEMA_VERSION, "BRAF", "gene_symbol", "MONDO:0005105", ("safety",), (), "Open Targets", "24.06", "different")
    first = build_target_feasibility_profiles((one, two), fetched)
    second = build_target_feasibility_profiles((two, one), fetched)
    assert first.batch_id == second.batch_id and first.coverage_is_scientific_confidence is False
    with pytest.raises(ValueError, match="duplicate"):
        build_target_feasibility_profiles((one, one), fetched)

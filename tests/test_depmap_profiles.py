"""Offline regression tests for descriptive Issue 503 dependency profiles."""
from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path
import shutil

from examples.depmap.run_dependency_profiles import main as profile_main
import pytest

from targetintel.functional_dependency import (
    DepMapIngestionRequest, DepMapModelContextDefinition, DepMapReleaseManifest,
    DepMapProfileError, DepMapTargetRequest, FunctionalDependencyProfilePolicy,
    build_dependency_profiles, ingest_local_release, write_dependency_profile_artifacts,
)
from targetintel.functional_dependency.depmap_ingestion import INGESTION_REQUEST_FORMAT_VERSION

ROOT = Path(__file__).parent / "fixtures" / "depmap"
INGESTION = ROOT / "ingestion"
PROFILES = ROOT / "profiles"


def context() -> DepMapModelContextDefinition:
    return DepMapModelContextDefinition.from_dict(json.loads((PROFILES / "melanoma_context.json").read_text()))


def policy() -> FunctionalDependencyProfilePolicy:
    return FunctionalDependencyProfilePolicy.from_dict(json.loads((PROFILES / "profile_policy.json").read_text()))


def ingest(tmp_path: Path) -> Path:
    manifest = DepMapReleaseManifest.from_dict(json.loads((INGESTION / "release_manifest.json").read_text()))
    request = DepMapIngestionRequest(INGESTION_REQUEST_FORMAT_VERSION, manifest, "target_subset", INGESTION.resolve(), (tmp_path / "ingestion").resolve(), target_universe=[DepMapTargetRequest("BRAF", "symbol"), DepMapTargetRequest("CDK4", "symbol"), DepMapTargetRequest("NRAS", "symbol"), DepMapTargetRequest("NONE", "symbol")])
    ingest_local_release(request)
    return tmp_path / "ingestion"


def ingest_source(tmp_path: Path, targets: list[str], changes: dict[str, str] | None = None, *, without_references: bool = False) -> Path:
    """Create a validated synthetic Issue 502 artifact set for one profile case."""
    source = tmp_path / "source"
    shutil.copytree(INGESTION, source)
    payload = json.loads((source / "release_manifest.json").read_text())
    if changes:
        for name, content in changes.items():
            (source / name).write_text(content, encoding="utf-8", newline="")
    if without_references:
        payload["file_manifests"] = [item for item in payload["file_manifests"] if item["dataset_role"] not in {"common_essential_reference", "pan_dependency_reference"}]
        payload["optional_dataset_roles"] = [role for role in payload["optional_dataset_roles"] if role not in {"common_essential_reference", "pan_dependency_reference"}]
    for item in payload["file_manifests"]:
        content = (source / item["relative_filename"]).read_bytes()
        item["expected_size_bytes"] = len(content)
        item["sha256_checksum"] = sha256(content).hexdigest()
    manifest = DepMapReleaseManifest.from_dict(payload)
    root = (tmp_path / "ingestion").resolve()
    request = DepMapIngestionRequest(INGESTION_REQUEST_FORMAT_VERSION, manifest, "target_subset", source.resolve(), root,
                                     target_universe=[DepMapTargetRequest(target, "symbol") for target in targets])
    ingest_local_release(request)
    return root


def test_context_and_policy_identities_are_order_independent_and_versioned() -> None:
    first = context()
    reordered = DepMapModelContextDefinition("v0.5.0", "melanoma", "fixture-v1", "depmap-modelid-v1", {"PrimaryDisease": ["Melanoma"]}, minimum_context_model_count=2, limitations=["Synthetic exact-metadata context only."])
    assert first.context_definition_id == reordered.context_definition_id
    assert first.context_definition_id != DepMapModelContextDefinition("v0.5.0", "melanoma", "fixture-v2", "depmap-modelid-v1", {"PrimaryDisease": ["Melanoma"]}).context_definition_id
    assert policy().profile_policy_id != FunctionalDependencyProfilePolicy("v0.5.0", 2, 1, 1, 2, [.6], "linear", "exclude_and_report", "gene_effect_median_strength_percentile", {}).profile_policy_id
    with pytest.raises(ValueError, match="target-specific"):
        FunctionalDependencyProfilePolicy("v0.5.0", 2, 1, 1, 2, [.5], "linear", "exclude_and_report", "gene_effect_median_strength_percentile", {"BRAF_threshold": .5})


def test_context_assignment_keeps_all_models_and_explicit_states(tmp_path: Path) -> None:
    root = ingest(tmp_path)
    excluded = DepMapModelContextDefinition("v0.5.0", "melanoma", "fixture-v1", "depmap-modelid-v1", {"PrimaryDisease": ["Melanoma"]}, explicit_model_exclusions=["ACH-001"])
    _, assignments = build_dependency_profiles(root.resolve(), excluded, policy())
    by_model = {item["model_identifier"]: item["assignment_status"] for item in assignments}
    assert by_model["ACH-001"] == "explicitly_excluded"
    assert by_model["ACH-004"] == "metadata_unavailable"
    assert by_model["ACH-007"] == "missing_required_metadata"
    assert len(by_model) == 7

    ambiguous = DepMapModelContextDefinition("v0.5.0", "melanoma", "fixture-v1", "depmap-modelid-v1", {"PrimaryDisease": ["Melanoma"]}, {"PrimaryDisease": ["Melanoma"]})
    _, ambiguous_assignments = build_dependency_profiles(root.resolve(), ambiguous, policy())
    assert {item["assignment_status"] for item in ambiguous_assignments} >= {"ambiguous_context"}


def test_context_assignment_preserves_metadata_only_models_as_not_reconciled(tmp_path: Path) -> None:
    metadata = (INGESTION / "model_metadata.csv").read_text(encoding="utf-8") + "ACH-008,Skin,Melanoma,Synthetic\n"
    root = ingest_source(tmp_path, ["BRAF"], {"model_metadata.csv": metadata})
    _, assignments = build_dependency_profiles(root, context(), policy())
    assignment = next(item for item in assignments if item["model_identifier"] == "ACH-008")
    assert assignment["assignment_status"] == "model_not_reconciled"
    assert assignment["assignment_reason"] == "model is present in metadata but absent from both dependency matrices"


def test_profiles_preserve_coverage_missingness_and_determinism(tmp_path: Path) -> None:
    root = ingest(tmp_path)
    run, assignments = build_dependency_profiles(root.resolve(), context(), policy())
    assert [item["assignment_status"] for item in assignments if item["model_identifier"] == "ACH-004"] == ["metadata_unavailable"]
    assert [item["assignment_status"] for item in assignments if item["model_identifier"] == "ACH-007"] == ["missing_required_metadata"]
    records = {item.target_identity["normalized_request"]: item.to_dict() for item in run.profiles}
    assert records["BRAF"]["payload"]["coverage_status"] == "sufficient_complete_coverage"
    assert records["CDK4"]["payload"]["matrix_coverage_status"] == "target_present_only_dependency_probability"
    assert records["CDK4"]["payload"]["coverage_status"] == "sufficient_partial_coverage"
    assert records["NONE"]["payload"]["coverage_status"] == "target_unresolved"
    assert records["BRAF"]["payload"]["common_essential_reference"]["status"] == "explicitly_present"
    assert records["BRAF"]["payload"]["pan_dependency_reference"]["status"] == "explicitly_absent"
    assert records["NRAS"]["payload"]["common_essential_reference"]["status"] == "explicitly_absent"
    assert records["NRAS"]["payload"]["pan_dependency_reference"]["status"] == "explicitly_present"
    assert any(item["type"] == "strong_negative_gene_effect_low_probability" for item in records["NRAS"]["payload"]["contradiction_observations"])
    assert records["BRAF"]["payload"]["summaries"]["context"]["gene_effect"]["median"] == -0.5
    assert records["BRAF"]["payload"]["summaries"]["context"]["dependency_probability"]["threshold_fractions"][0] == {"threshold": .5, "numerator": 3, "denominator": 3, "fraction": 1.0}
    contrasts = records["BRAF"]["payload"]["contrasts"]
    assert contrasts["dependency_probability_context_minus_non_context_threshold_fractions"] == [
        {"threshold": .5, "context_fraction": 1.0, "non_context_fraction": pytest.approx(2 / 3), "difference": pytest.approx(1 / 3)},
        {"threshold": .8, "context_fraction": pytest.approx(2 / 3), "non_context_fraction": 0.0, "difference": pytest.approx(2 / 3)},
    ]
    pan_contrasts = contrasts["context_minus_pan_cancer"]
    assert pan_contrasts["gene_effect_median"] == pytest.approx(-.1)
    assert pan_contrasts["gene_effect_mean"] == pytest.approx(-.08571428571428574)
    assert pan_contrasts["dependency_probability_median"] == pytest.approx(.15)
    assert [item["threshold"] for item in pan_contrasts["dependency_probability_threshold_fractions"]] == [.5, .8]
    assert all(set(item) == {"threshold", "context_fraction", "pan_cancer_fraction", "difference"} for item in pan_contrasts["dependency_probability_threshold_fractions"])
    assert len(records["BRAF"]["payload"]["lineage_summaries"]) >= 3
    assert records["BRAF"]["payload"]["empirical_context_lineage_position"]["available"] is True
    assert run.run_id == build_dependency_profiles(root.resolve(), context(), policy())[0].run_id


def test_example_writes_stable_operational_artifacts(tmp_path: Path, monkeypatch) -> None:
    root = ingest(tmp_path)
    output = (tmp_path / "profiles").resolve()
    monkeypatch.setattr("sys.argv", ["run_dependency_profiles.py", "--ingestion-dir", str(root.resolve()), "--context", str((PROFILES / "melanoma_context.json").resolve()), "--policy", str((PROFILES / "profile_policy.json").resolve()), "--output-dir", str(output)])
    assert profile_main() == 0
    for name in ("dependency_profile_manifest.json", "dependency_profiles.jsonl", "dependency_profile_summary.tsv", "dependency_coverage_summary.json", "model_context_index.tsv"):
        assert (output / name).is_file()
    assert "target-quality score" not in (output / "dependency_profile_summary.tsv").read_text()


def test_manifest_is_not_written_when_a_dependent_artifact_fails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = ingest(tmp_path)
    run, assignments = build_dependency_profiles(root.resolve(), context(), policy())
    original_write_text = Path.write_text

    def fail_summary_write(path: Path, text: str, *args, **kwargs):
        if path.name == ".dependency_profile_summary.tsv.tmp":
            raise OSError("synthetic write failure")
        return original_write_text(path, text, *args, **kwargs)

    monkeypatch.setattr(Path, "write_text", fail_summary_write)
    with pytest.raises(OSError, match="synthetic write failure"):
        write_dependency_profile_artifacts((tmp_path / "failed-profiles").resolve(), run, assignments)
    assert not (tmp_path / "failed-profiles" / "dependency_profile_manifest.json").exists()


def test_equivalent_output_directories_have_identical_scientific_artifacts(tmp_path: Path) -> None:
    root = ingest(tmp_path)
    run, assignments = build_dependency_profiles(root.resolve(), context(), policy())
    first, second = (tmp_path / "first-profiles").resolve(), (tmp_path / "second-profiles").resolve()
    write_dependency_profile_artifacts(first, run, assignments)
    write_dependency_profile_artifacts(second, run, assignments)
    for name in ("dependency_profile_manifest.json", "dependency_profiles.jsonl", "dependency_profile_summary.tsv", "dependency_coverage_summary.json", "model_context_index.tsv"):
        assert (first / name).read_bytes() == (second / name).read_bytes()
    assert "p_value" not in (first / "dependency_profiles.jsonl").read_text()


@pytest.mark.parametrize("artifact, replacement", [
    ("model_index.tsv", ("Skin", "Other", 1)),
    ("gene_index.tsv", ("BRAF (673)", "BRAF_CHANGED (673)", 1)),
    ("reference_index.tsv", ("BRAF (673)", "BRAF_CHANGED (673)", 1)),
    ("gene_effect_subset.tsv", ("-0.5", "-0.51", 1)),
])
def test_profile_rejects_derived_artifacts_with_snapshot_identity_mismatch(tmp_path: Path, artifact: str, replacement: tuple[str, str, int]) -> None:
    root = ingest(tmp_path)
    path = root / artifact
    old, new, count = replacement
    path.write_text(path.read_text(encoding="utf-8").replace(old, new, count), encoding="utf-8", newline="")
    with pytest.raises(DepMapProfileError, match="identity does not match ingestion snapshot"):
        build_dependency_profiles(root.resolve(), context(), policy())


def test_coverage_states_references_and_lineage_edge_cases_remain_explicit(tmp_path: Path) -> None:
    no_context = DepMapModelContextDefinition("v0.5.0", "unrepresented", "fixture-v1", "depmap-modelid-v1", {"PrimaryDisease": ["Absent"]})
    root = ingest_source(tmp_path / "no-context", ["BRAF"])
    assert build_dependency_profiles(root, no_context, policy())[0].profiles[0].payload["coverage_status"] == "no_context_models"

    missing_effect = (INGESTION / "gene_effect.csv").read_text().replace("ACH-001,-0.5", "ACH-001,").replace("ACH-002,-0.6", "ACH-002,").replace("ACH-003,-0.4", "ACH-003,")
    missing_probability = (INGESTION / "dependency_probability.csv").read_text().replace("ACH-001,0.9", "ACH-001,").replace("ACH-002,0.8", "ACH-002,").replace("ACH-003,0.7", "ACH-003,")
    root = ingest_source(tmp_path / "missing", ["BRAF"], {"gene_effect.csv": missing_effect, "dependency_probability.csv": missing_probability})
    assert build_dependency_profiles(root, context(), policy())[0].profiles[0].payload["coverage_status"] == "context_models_all_values_missing"

    root = ingest_source(tmp_path / "only-effect", ["BRAF"], {"dependency_probability.csv": "\n".join(
        [line.replace(",BRAF (673)", "", 1) if number == 0 else ",".join(line.split(",")[0:1] + line.split(",")[2:]) for number, line in enumerate((INGESTION / "dependency_probability.csv").read_text().splitlines())]
    ) + "\n"})
    only_effect = build_dependency_profiles(root, context(), policy())[0].profiles[0].payload
    assert only_effect["matrix_coverage_status"] == "target_present_only_gene_effect"
    assert {item["type"] for item in only_effect["contradiction_observations"]} >= {"context_signal_present_only_one_matrix", "insufficient_data_for_concordance_assessment"}

    strict_context = FunctionalDependencyProfilePolicy("v0.5.0", 4, 1, 1, 2, [.5], "linear", "exclude_and_report", "gene_effect_median_strength_percentile", {})
    strict_context_payload = build_dependency_profiles(ingest_source(tmp_path / "context-minimum", ["BRAF"]), context(), strict_context)[0].profiles[0].payload
    assert strict_context_payload["coverage_status"] == "insufficient_measured_context_models"
    assert strict_context_payload["contrasts"]["gene_effect_context_minus_non_context_median"] is None
    assert strict_context_payload["contrasts"]["gene_effect_context_minus_non_context_mean"] is None
    assert strict_context_payload["contrasts"]["dependency_probability_context_minus_non_context_median"] is None
    assert strict_context_payload["contrasts"]["dependency_probability_context_minus_non_context_threshold_fractions"] == ()
    assert all(value is None or value == () for value in strict_context_payload["contrasts"]["context_minus_pan_cancer"].values())
    assert strict_context_payload["contrasts"]["direction"] == "Negative gene-effect context-minus-reference values indicate stronger model dependency signal in the context group."
    strict_reference = FunctionalDependencyProfilePolicy("v0.5.0", 2, 5, 2, 2, [.5], "linear", "exclude_and_report", "gene_effect_median_strength_percentile", {})
    strict_payload = build_dependency_profiles(ingest_source(tmp_path / "reference-minimum", ["BRAF"]), context(), strict_reference)[0].profiles[0].payload
    assert strict_payload["coverage_status"] == "insufficient_measured_reference_models"
    assert strict_payload["contrasts"]["gene_effect_context_minus_non_context_median"] is None
    assert strict_payload["contrasts"]["gene_effect_context_minus_non_context_mean"] is None
    assert strict_payload["contrasts"]["dependency_probability_context_minus_non_context_median"] is None
    assert strict_payload["contrasts"]["dependency_probability_context_minus_non_context_threshold_fractions"] == ()
    assert strict_payload["contrasts"]["context_minus_pan_cancer"]["gene_effect_median"] is not None
    assert strict_payload["contrasts"]["context_minus_pan_cancer"]["dependency_probability_median"] is not None
    assert strict_payload["contrasts"]["context_minus_pan_cancer"]["dependency_probability_threshold_fractions"]
    assert any(not item["eligible"] for item in strict_payload["lineage_summaries"])

    unavailable = build_dependency_profiles(ingest_source(tmp_path / "references", ["BRAF"], without_references=True), context(), policy())[0].profiles[0].payload
    assert unavailable["common_essential_reference"]["status"] == "reference_unavailable"
    assert unavailable["pan_dependency_reference"]["status"] == "reference_unavailable"


def test_remaining_contradictions_and_ties_are_deterministic(tmp_path: Path) -> None:
    root = ingest_source(tmp_path / "references", ["BRAF"])
    run, _ = build_dependency_profiles(root, context(), policy())
    payload = run.profiles[0].payload
    assert any(item["type"] == "optional_reference_membership_conflicts_with_descriptive_context_selectivity" for item in payload["contradiction_observations"])
    tied_effect = (INGESTION / "gene_effect.csv").read_text().replace("ACH-005,-0.1", "ACH-005,-0.5")
    tied_root = ingest_source(tmp_path / "tied", ["BRAF"], {"gene_effect.csv": tied_effect})
    tied_first = build_dependency_profiles(tied_root, context(), policy())[0]
    tied_second = build_dependency_profiles(tied_root, context(), policy())[0]
    assert tied_first.run_id == tied_second.run_id
    assert tied_first.profiles[0].payload["empirical_context_lineage_position"] == tied_second.profiles[0].payload["empirical_context_lineage_position"]

"""Publication contract coverage using a synthetic closure, never real data."""
from __future__ import annotations

import csv
import json
from pathlib import Path
import shutil

import pytest

from targetintel.functional_dependency.publication import DepMapPublicationError, publish_depmap_v050


def _prepared_closure(tmp_path: Path) -> tuple[Path, Path, Path, Path]:
    root = tmp_path / "fixture"
    shutil.copytree("tests/fixtures/depmap/report_snapshot", root)
    run, config, manifests = root / "run", root / "config", root / "manifests"
    replacements = {
        "v050rc_fixture": "v050rc_fe68644624acd4b72aaf289baa9380c07f30d26c3271923ba81540f9b91e37b6",
        "dmrm_fixture": "dmrm_08d15741ac2297df953346ff257dec05feb0b754a62ae6a9f56573e11801c5b1",
        "v050closure_fixture": "v050closure_e57fa135ff266078d2170bf2a34df094f7888e7ce6002783c75f6a583690a3a4",
    }
    for path in (*run.rglob("*.json"), *config.rglob("*.json"), *manifests.rglob("*.json")):
        text = path.read_text()
        for old, new in replacements.items():
            text = text.replace(old, new)
        path.write_text(text)
    closure = json.loads((run / "release_closure_manifest.json").read_text())
    closure["scientific_closure_identity"] = replacements["v050closure_fixture"]
    (run / "release_closure_manifest.json").write_text(json.dumps(closure))
    preflight = json.loads((run / "release_preflight.json").read_text())
    preflight["source_files"] = [
        {"filename": "CRISPRGeneEffect.csv", "sha256": "0" * 64, "byte_size": 1, "role": "gene effect"},
        {"filename": "CRISPRGeneDependency.csv", "sha256": "1" * 64, "byte_size": 1, "role": "dependency probability"},
        {"filename": "Model.csv", "sha256": "2" * 64, "byte_size": 1, "role": "model metadata"},
    ]
    (run / "release_preflight.json").write_text(json.dumps(preflight))
    payload = {"terminal_status": "valid", "payload": {"target_resolution_status": "resolved_exact", "coverage_status": "sufficient_complete_coverage", "matrix_coverage_status": "resolved", "model_coverage": {"context_model_count": 2, "non_context_model_count": 3, "pan_cancer_model_count": 5}, "summaries": {"context": {"gene_effect": {"median": -0.8, "measured_model_count": 2}, "dependency_probability": {"median": 0.7, "measured_model_count": 2}}, "non_context": {"gene_effect": {"median": -0.2, "measured_model_count": 3}}}, "contrasts": {}, "empirical_context_lineage_position": {}, "limitations": ["Descriptive research-preview evidence only."]}}
    profiles = run / "profiles" / "dependency_profiles.jsonl"
    profiles.write_text("".join(json.dumps({"target_identity": {"normalized_request": f"G{i:03d}", "canonical_identity": f"G{i:03d}:{i + 1}"}, **payload}) + "\n" for i in range(331)))
    (run / "integration" / "candidate_overlay.tsv").write_text(
        "original_target_identifier\tbaseline_rank\tbaseline_score\tcandidate_rank\tprofile_available\n"
        + "".join(f"G{i:03d}\t{i + 1}\t0.0\t{i + 1}\tTrue\n" for i in range(300))
    )
    ranked = tmp_path / "ranked.tsv"
    ranked.write_text("target_symbol\n" + "".join(f"G{i:03d}\n" for i in range(300)))
    return run, config, manifests, ranked


@pytest.fixture
def published_bundle(tmp_path: Path) -> Path:
    run, config, manifests, ranked = _prepared_closure(tmp_path)
    return publish_depmap_v050(run_dir=run, config_dir=config, manifest_dir=manifests, output_dir=tmp_path / "bundle", ranked_targets=ranked)


def test_publication_has_complete_aggregate_inventory_and_profiles(published_bundle: Path) -> None:
    profiles = list(csv.DictReader((published_bundle / "selected_target_profiles.tsv").open(), delimiter="\t"))
    inventory = list(csv.DictReader((published_bundle / "publication_inventory.tsv").open(), delimiter="\t"))
    assert len(profiles) == 331 and len({row["target"] for row in profiles}) == 331
    assert {row["source_artifact_name"] for row in inventory} >= {"CRISPRGeneEffect.csv", "CRISPRGeneDependency.csv", "Model.csv"}
    assert all(row["exclusion_reason"] for row in inventory if row["publication_action"] == "excluded")
    assert not any(path.name == "dependency_profiles.jsonl" for path in published_bundle.rglob("*"))
    assert all(path.stat().st_size <= 5 * 1024 * 1024 for path in published_bundle.rglob("*") if path.is_file())


def test_publication_sanitizes_local_operational_metadata(tmp_path: Path) -> None:
    run, config, manifests, ranked = _prepared_closure(tmp_path)
    (run / "release_report.md").write_text("host S6445-MD61213 mount 5EC8-12FA")
    bundle = publish_depmap_v050(run_dir=run, config_dir=config, manifest_dir=manifests, output_dir=tmp_path / "bundle", ranked_targets=ranked)
    published = (bundle / "release_report.md").read_text()
    assert "S6445-MD61213" not in published and "5EC8-12FA" not in published


def test_publication_preserves_official_https_urls(tmp_path: Path) -> None:
    run, config, manifests, ranked = _prepared_closure(tmp_path)
    bundle = publish_depmap_v050(run_dir=run, config_dir=config, manifest_dir=manifests,
                                 output_dir=tmp_path / "bundle", ranked_targets=ranked)
    source_manifest = json.loads((bundle / "source_manifest.json").read_text())
    assert source_manifest["official_download_url"] == "https://depmap.org/portal/data_page/?release=DepMap+Public+26Q1"
    assert source_manifest["official_release_notes_url"] == "https://forum.depmap.org/t/announcing-the-26q1-release/4606"


def test_publication_relabels_inherited_fixture_limitations_for_real_release(tmp_path: Path) -> None:
    run, config, manifests, ranked = _prepared_closure(tmp_path)
    profiles = run / "profiles" / "dependency_profiles.jsonl"
    profiles.write_text(profiles.read_text().replace(
        "Descriptive research-preview evidence only.",
        "Descriptive synthetic-fixture evidence only; no therapeutic, clinical, safety, or causal conclusion.",
    ))
    bundle = publish_depmap_v050(run_dir=run, config_dir=config, manifest_dir=manifests,
                                 output_dir=tmp_path / "bundle", ranked_targets=ranked)
    evidence = (bundle / "dependency_report_evidence.jsonl").read_text()
    assert "Descriptive synthetic-fixture evidence only" not in evidence
    assert "Descriptive real-release aggregate evidence only" in evidence


def test_publication_rejects_a_non_300_gene_baseline(tmp_path: Path) -> None:
    run, config, manifests, ranked = _prepared_closure(tmp_path)
    ranked.write_text("target_symbol\nG000\n")
    with pytest.raises(DepMapPublicationError, match="exactly 300"):
        publish_depmap_v050(run_dir=run, config_dir=config, manifest_dir=manifests,
                             output_dir=tmp_path / "bundle", ranked_targets=ranked)


def test_publication_tsv_files_do_not_end_lines_with_whitespace(
    published_bundle: Path,
) -> None:
    for path in sorted(published_bundle.glob("*.tsv")):
        for line_number, line in enumerate(
            path.read_bytes().splitlines(),
            start=1,
        ):
            assert not line.endswith(
                (b" ", b"\t")
            ), (
                f"{path.name}:{line_number} ends with "
                "trailing whitespace"
            )


def test_real_markdown_cards_end_with_single_newline() -> None:
    card_dir = Path(
        "examples/target_cards/depmap_26q1"
    )
    cards = sorted(card_dir.glob("*.md"))

    assert len(cards) == 331

    for path in cards:
        raw = path.read_bytes()

        assert raw.endswith(b"\n"), (
            f"{path} does not end with a newline"
        )
        assert not raw.endswith(b"\n\n"), (
            f"{path} ends with a blank line"
        )


def test_real_html_indexes_have_no_trailing_whitespace() -> None:
    paths = [
        Path("examples/html_reports/depmap_26q1/index.html"),
        Path(
            "examples/html_reports/depmap_26q1/"
            "targets/index.html"
        ),
    ]

    for path in paths:
        raw = path.read_bytes()

        assert raw.endswith(b"\n")
        assert not raw.endswith(b"\n\n")

        for line_number, line in enumerate(
            raw.splitlines(),
            start=1,
        ):
            assert not line.endswith(
                (b" ", b"\t")
            ), (
                f"{path}:{line_number} contains "
                "trailing whitespace"
            )

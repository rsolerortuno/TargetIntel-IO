#!/usr/bin/env python3
"""Fully offline, deterministic v0.4.0 feasibility composition demonstration."""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

import pandas as pd

from targetintel.feasibility import (
    OpenTargetsFetchRequest, OpenTargetsTransportResponse, TargetFeasibilityRequest,
    build_target_feasibility_profile, fetch_opentargets,
)
from targetintel.feasibility.models import REQUEST_SCHEMA_ID, REQUEST_SCHEMA_VERSION
from targetintel.feasibility.opentargets_transport import FakeOpenTargetsTransport
from targetintel.hypothesis_cards import make_target_card
from targetintel.html_reports import make_target_html_report
from targetintel.modality import assign_modality_fit, compose_modality_with_feasibility

ROOT = Path(__file__).resolve().parent
FIXTURE = ROOT / "fixtures" / "mock_opentargets_responses.json"
UNIVERSE = ROOT / "fixtures" / "target_universe.json"
RELEASE = "24.06"


def _write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(value, str):
        path.write_text(value, encoding="utf-8")
    else:
        path.write_text(json.dumps(_plain(value), indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _plain(value: Any) -> Any:
    """Serialize immutable contract mappings without changing their content."""
    if isinstance(value, Mapping):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_plain(item) for item in value]
    if isinstance(value, list):
        return [_plain(item) for item in value]
    return value


def _response(operation: str, payload: dict) -> OpenTargetsTransportResponse:
    return OpenTargetsTransportResponse(operation, 200, payload, source_release=RELEASE)


def _transports(fixture: dict) -> tuple[FakeOpenTargetsTransport, FakeOpenTargetsTransport]:
    ranked = FakeOpenTargetsTransport({
        "association_page_0": _response("association_page_0", {"data": {"disease": {
            "id": fixture["disease_id"], "associatedTargets": {
                "count": len(fixture["association_ranked_rows"]), "rows": fixture["association_ranked_rows"]
            }}}})
    })
    directed: dict[str, Any] = {}
    for symbol, item in fixture["targets"].items():
        if item.get("unresolved"):
            directed[f"resolve_{symbol}"] = _response(f"resolve_{symbol}", {"data": {"search": {"hits": []}}})
            continue
        gene = item["ensembl"]
        directed[f"resolve_{symbol}"] = _response(f"resolve_{symbol}", {"data": {"search": {"hits": [{"id": gene, "entity": "TARGET"}]}}})
        key = f"target_candidate_{symbol}_{gene}"
        if item.get("failure"):
            directed[key] = RuntimeError("synthetic_retrieval_failure")
        elif item.get("no_record"):
            directed[key] = _response(key, {"data": {"target": None}})
        else:
            directed[key] = _response(key, {"data": {"target": {"id": gene, "approvedSymbol": symbol, **item["fields"]}}})
    return ranked, FakeOpenTargetsTransport(directed)


def _profile_request(symbol: str) -> TargetFeasibilityRequest:
    return TargetFeasibilityRequest(
        REQUEST_SCHEMA_ID, REQUEST_SCHEMA_VERSION, symbol, "gene_symbol", "MONDO:0005105",
        ("clinical_precedence", "tractability", "doability", "safety"),
        ("antibody", "small_molecule", "protac", "other_clinical"),
        "Open Targets", RELEASE, "v0.4.0-offline-demo",
    )


def _ranked_row() -> pd.Series:
    return pd.Series({
        "target_symbol": "TAP1", "target_name": "Transporter 1", "role_classification": "resistance biomarker",
        "therapeutic_direction": "stratify", "resistance_axis": "antigen presentation",
        "target_score": 0.71, "score_components": "synthetic_component=0.71",
        "antibody_io_score": 0.20, "biomarker_score": 0.88, "small_molecule_score": 0.11,
        "antibody_io_rank": 2, "biomarker_rank": 1, "small_molecule_rank": 3,
        "best_modality": "patient stratification", "modality_rationale": "Existing deterministic rationale.",
        "evidence_for": "Synthetic pre-ranking evidence", "evidence_against": "Synthetic limitation",
        "rationale": "Existing ranked-card rationale.", "priority": "high",
    })


def _protected(row: pd.Series) -> dict[str, Any]:
    return {
        "target_scores": {"TAP1": row["target_score"]}, "score_components": {"TAP1": row["score_components"]},
        "biological_roles": {"TAP1": row["role_classification"]}, "therapeutic_intent_labels": {"TAP1": row["therapeutic_direction"]},
        "therapeutic_intent_scores": {key: row[key] for key in ("antibody_io_score", "biomarker_score", "small_molecule_score")},
        "target_ranks": {key: row[key] for key in ("antibody_io_rank", "biomarker_rank", "small_molecule_rank")},
        "target_ordering": ["TAP1"], "selected_target_set": ["TAP1"],
        "feature_table_values": {"TAP1": {"resistance_axis": row["resistance_axis"], "target_name": row["target_name"]}},
    }


def run_demo(output_dir: str | Path) -> dict[str, Any]:
    """Use only v0.4.0 public APIs and a fake injected transport boundary."""
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    universe = json.loads(UNIVERSE.read_text(encoding="utf-8"))["directed_target_universe"]
    ranked_transport, directed_transport = _transports(fixture)
    ranked_request = OpenTargetsFetchRequest(query_type="association_ranked", disease_id=fixture["disease_id"], requested_source_release=RELEASE)
    directed_request = OpenTargetsFetchRequest(query_type="directed_target_universe", target_universe=universe, disease_id=fixture["disease_id"], requested_source_release=RELEASE)
    ranked = fetch_opentargets(ranked_request, ranked_transport)
    directed = fetch_opentargets(directed_request, directed_transport)
    # The Issue 402 contract exposes a no-record terminal state for an explicit
    # Ensembl universe.  Keep this separate from symbol resolution: a symbol
    # cannot be declared resolved without a target record to validate it.
    no_record_identifier = fixture["targets"]["NOREC"]["ensembl"]
    no_record_request = OpenTargetsFetchRequest(
        query_type="directed_target_universe", target_identifier_type="ensembl_gene_id",
        target_universe=[no_record_identifier], requested_source_release=RELEASE,
    )
    no_record = fetch_opentargets(no_record_request, FakeOpenTargetsTransport({
        f"target_{no_record_identifier}": _response(f"target_{no_record_identifier}", {"data": {"target": None}})
    }))
    if ranked.status != "completed" or directed.status != "completed_with_gaps" or no_record.status != "completed_with_gaps":
        raise RuntimeError("offline retrieval validation failed")
    coverage = directed.coverage_report
    terminal = coverage.terminal_categories
    if coverage.coverage_denominator != len(universe) or sum(len(v) for v in terminal.values()) != len(universe):
        raise RuntimeError("not every directed target has a terminal outcome")

    builds = {symbol: build_target_feasibility_profile(_profile_request(symbol), directed) for symbol in ("TAP1", "IFNGR1", "STAT1")}
    if any(result.profile is None for result in builds.values()):
        raise RuntimeError("successful records did not build profiles")
    tap1 = builds["TAP1"].profile
    assert tap1 is not None
    annotations = {}
    legacy = assign_modality_fit("TAP1")
    legacy_before = dict(legacy.__dict__)
    for modality in ("antibody", "small_molecule", "protac"):
        composed = compose_modality_with_feasibility(legacy, tap1, modality, target_identifier="TAP1", target_identifier_type="gene_symbol")
        annotations[modality] = composed.feasibility_annotation
        if not composed.scores_unmodified or not composed.rankings_unmodified or not composed.no_recommendation_generated:
            raise RuntimeError("modality composition invariant failed")
    protac_observations = [item for item in tap1.observations if item.modality == "protac" and item.availability_state == "observed"]
    if dict(legacy.__dict__) != legacy_before or protac_observations:
        raise RuntimeError("legacy mutation or PROTAC inference detected")

    row = _ranked_row(); protected_before = _protected(row)
    markdown = make_target_card(row, feasibility_annotations=tuple(annotations.values()), feasibility_target_identifier_type="gene_symbol")
    html = make_target_html_report(row, feasibility_annotations=tuple(annotations.values()), feasibility_target_identifier_type="gene_symbol")
    protected_after = _protected(row)
    if protected_before != protected_after:
        raise RuntimeError("protected output invariant failed")
    _write(out / "cards" / "TAP1.md", markdown)
    _write(out / "reports" / "TAP1.html", html)
    _write(out / "coverage_summary.json", {"coverage_id": coverage.coverage_id, "coverage_numerator": coverage.coverage_numerator, "coverage_denominator": coverage.coverage_denominator, "coverage_fraction": coverage.coverage_fraction, "coverage_is_scientific_confidence": False, "terminal_categories": dict(terminal), "truncated": coverage.truncated})
    _write(out / "protected_invariants.json", {"protected_outputs_unchanged": True, "before": protected_before, "after": protected_after})

    ranked_symbols = [record.approved_symbol for record in ranked.records]
    recovered = sorted(set(coverage.terminal_categories["resolved_and_retrieved"]).difference(ranked_symbols))
    summary = {
        "demo_format_version": "v0.4.0", "offline": True, "research_only": True, "no_live_transport": True, "no_llm": True,
        "source_release": directed.observed_source_release, "release_verification_state": directed.release_verification_state,
        "query_schema_version": directed.request.query_schema_version, "target_universe_hash": directed.request.target_universe_hash,
        "ranked_target_identifiers": ranked_symbols, "directed_requested_targets": list(directed.request.target_universe),
        "directed_resolved_targets": sorted(set(terminal["resolved_and_retrieved"]) | set(terminal["resolved_no_record"])),
        "directed_retrieved_targets": list(terminal["resolved_and_retrieved"]), "absent_from_ranked_recovered_by_directed": recovered,
        "unresolved_targets": list(terminal["unresolved"]), "no_record_targets": list(no_record.coverage_report.terminal_categories["resolved_no_record"]), "failed_targets": list(terminal["retrieval_failed"]),
        "truncated": coverage.truncated, "coverage_numerator": coverage.coverage_numerator, "coverage_denominator": coverage.coverage_denominator,
        "coverage_is_scientific_confidence": False, "fetch_result_id": directed.result_id, "coverage_id": coverage.coverage_id,
        "query_plan_id": directed.query_plan.plan_id, "cache_identity": directed.cache_identity,
        "record_ids": [record.record_id for record in directed.records], "payload_ids": [record.raw_payload_id for record in directed.records],
        "profile_ids": {symbol: result.profile.profile_id for symbol, result in builds.items() if result.profile},
        "modality_annotation_ids": {modality: annotation.annotation_id for modality, annotation in annotations.items()},
        "presentation_section_ids": {"TAP1": next(iter(annotations.values())).presentation_section_id if hasattr(next(iter(annotations.values())), "presentation_section_id") else None},
        "safety_data_states": {"TAP1": "source-linked safety observation", "IFNGR1": "insufficient safety data", "STAT1": "no signal in successfully retrieved safety records"},
        "contradictions_retained": tap1.contradiction_indicators, "protected_outputs_unchanged": True,
    }
    # Obtain the canonical presentation identity from the renderer-created section without reimplementing it.
    from targetintel.feasibility.presentation import make_feasibility_report_section
    section = make_feasibility_report_section(
        target_identifier="TAP1", target_identifier_type="gene_symbol", annotations=tuple(annotations.values())
    )
    summary["presentation_section_ids"] = {"TAP1": section.section_id}
    _write(out / "demo_summary.json", summary)
    hashes = {str(path.relative_to(out)): hashlib.sha256(path.read_bytes()).hexdigest() for path in sorted(out.rglob("*")) if path.is_file()}
    manifest = {"demo_format_version": "v0.4.0", "source_release": directed.observed_source_release, "release_verification_state": directed.release_verification_state, "query_schema_version": directed.request.query_schema_version, "target_universe_hash": directed.request.target_universe_hash, "fetch_result_id": directed.result_id, "query_plan_id": directed.query_plan.plan_id, "cache_identity": directed.cache_identity, "coverage_id": coverage.coverage_id, "record_ids": summary["record_ids"], "payload_ids": summary["payload_ids"], "profile_ids": summary["profile_ids"], "modality_annotation_ids": summary["modality_annotation_ids"], "presentation_section_ids": summary["presentation_section_ids"], "output_content_hashes": hashes, "protected_outputs_unchanged": True}
    _write(out / "demo_manifest.json", manifest)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the fully offline deterministic v0.4.0 feasibility demo.")
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()
    try:
        run_demo(args.output_dir)
    except Exception as exc:
        print(f"Demo failed: {exc}")
        return 1
    print("Offline research-only v0.4.0 feasibility demo completed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Publish a sanitized, portable DepMap Public 26Q1 report bundle offline."""
from __future__ import annotations

import argparse
import csv
from html import escape
from pathlib import Path
import json
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pandas as pd

from targetintel.functional_dependency.publication import publish_depmap_v050, validate_publication_tree
from targetintel.functional_dependency.report_loader import load_dependency_report_evidence_bundle
from targetintel.functional_dependency.presentation import render_dependency_html, render_dependency_markdown
from targetintel.hypothesis_cards import write_top_target_cards
from targetintel.html_reports import write_html_index, write_top_html_reports


_SYNTHETIC_FIXTURE_LIMITATION = (
    "Descriptive synthetic-fixture evidence only; no therapeutic, clinical, "
    "safety, or causal conclusion."
)
_REAL_RELEASE_LIMITATION = (
    "Descriptive real-release aggregate evidence only; no therapeutic, clinical, "
    "safety, or causal conclusion."
)


def _real_release_markdown(evidence_item: object) -> str:
    """Keep inherited fixture wording out of a real-release publication."""
    return render_dependency_markdown(evidence_item).replace(
        _SYNTHETIC_FIXTURE_LIMITATION, _REAL_RELEASE_LIMITATION
    )


def _real_release_html(evidence_item: object) -> str:
    """Render the same truthful limitation in the HTML publication boundary."""
    return render_dependency_html(evidence_item).replace(
        _SYNTHETIC_FIXTURE_LIMITATION, _REAL_RELEASE_LIMITATION
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("run-dir", "config-dir", "manifest-dir", "output-dir", "html-output-dir", "ranked-targets", "cards-output-dir"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    bundle = publish_depmap_v050(run_dir=args.run_dir, config_dir=args.config_dir,
        manifest_dir=args.manifest_dir, output_dir=args.output_dir,
        ranked_targets=args.ranked_targets)
    evidence = load_dependency_report_evidence_bundle(bundle)
    ranked = pd.read_csv(args.ranked_targets, sep=None, engine="python")
    if "target_symbol" not in ranked and "original_target_identifier" in ranked:
        ranked = ranked.rename(columns={"original_target_identifier": "target_symbol"})
    if "target_symbol" not in ranked:
        raise ValueError("ranked-targets must contain target_symbol")
    productive = set(ranked["target_symbol"].astype(str))
    args.cards_output_dir.mkdir(parents=True, exist_ok=True)
    benchmark_membership: dict[str, str] = {}
    with (bundle / "benchmark_universe.tsv").open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle, delimiter="\t"):
            symbol = row.get("original_identifier")
            if symbol:
                benchmark_membership[symbol] = row.get("partition") or "recorded; partition unavailable"
    # The published real-release reports require the frozen authoritative
    # three-intent productive baseline.  The closure overlay is not a
    # substitute for any of these independently calculated score/rank pairs.
    top_n = len(ranked)
    target_dir = args.html_output_dir / "targets"
    target_dir.mkdir(parents=True, exist_ok=True)
    required_baseline_columns = {
        "antibody_io_final_score", "antibody_io_rank",
        "biomarker_final_score", "biomarker_rank",
        "small_molecule_final_score", "small_molecule_rank",
    }
    missing_baseline_columns = sorted(required_baseline_columns - set(ranked.columns))
    if missing_baseline_columns:
        raise ValueError(
            "ranked-targets must contain the complete authoritative three-intent "
            f"baseline; missing: {', '.join(missing_baseline_columns)}"
        )
    write_top_target_cards(ranked, output_dir=args.cards_output_dir, top_n_per_mode=top_n,
        dependency_evidence_by_symbol={key: value for key, value in evidence.items() if key in productive})
    write_top_html_reports(ranked, output_dir=target_dir, top_n_per_mode=top_n,
        dependency_evidence_by_symbol={key: value for key, value in evidence.items() if key in productive})
    write_html_index(ranked, output_dir=args.html_output_dir, top_n_per_mode=top_n,
        dependency_evidence_by_symbol=evidence, target_report_href_prefix="targets/")
    discovery = [{"target_symbol": symbol, "profile_available": item.profile_available,
        "coverage_status": item.coverage_status, "baseline_rank": item.baseline_rank,
        "dependency_aware_candidate_rank": item.dependency_aware_candidate_rank, "rank_delta": item.rank_delta,
        "productive_baseline": symbol in productive,
        "benchmark_member": "yes" if symbol in benchmark_membership else "no",
        "holdout_member": "yes" if benchmark_membership.get(symbol) == "holdout" else ("no" if symbol in benchmark_membership else "not recorded")}
        for symbol, item in evidence.items()]
    for symbol, item in evidence.items():
        if symbol in productive:
            continue
        markdown = ("# " + symbol + " — DepMap research-preview discovery identity\n\n"
            "This identity is part of the research-preview discovery universe and is not part of the authoritative productive baseline.\n\n"
            + _real_release_markdown(item))
        (args.cards_output_dir / f"{symbol}.md").write_text(markdown, encoding="utf-8")
        html = ("<!doctype html><meta charset=\"utf-8\"><title>" + symbol +
            " — DepMap research preview</title><h1>" + symbol +
            "</h1><p>This identity is part of the research-preview discovery universe and is not part of the authoritative productive baseline.</p>" +
            _real_release_html(item))
        (target_dir / f"{symbol}.html").write_text(html, encoding="utf-8")
    available = [row for row in discovery if row["profile_available"]]
    unavailable = [row for row in discovery if not row["profile_available"]]
    moved = [row for row in discovery if row["rank_delta"] is not None]
    upward = sorted(moved, key=lambda row: (row["rank_delta"], row["target_symbol"]))[:10]
    downward = sorted(moved, key=lambda row: (-row["rank_delta"], row["target_symbol"]))[:10]
    def table(rows: list[dict[str, object]]) -> str:
        cells = []
        for row in rows:
            membership = "productive baseline" if row["productive_baseline"] else "discovery-only"
            cells.append("<tr>" + "".join("<td>" + escape(str(value if value is not None else "not available")) + "</td>" for value in (row["target_symbol"], membership, row["profile_available"], row["coverage_status"], row["baseline_rank"], row["dependency_aware_candidate_rank"], row["rank_delta"], row["benchmark_member"], row["holdout_member"])) + "</tr>")
        return "<table><thead><tr><th>Target</th><th>Membership</th><th>Profile available</th><th>Coverage</th><th>Baseline rank</th><th>Research-preview DepMap overlay rank</th><th>Rank delta</th><th>Benchmark</th><th>Holdout</th></tr></thead><tbody>" + "".join(cells) + "</tbody></table>"
    overlay_html = ("<!doctype html><meta charset=\"utf-8\"><title>DepMap discovery overlay</title>"
        "<h1>DepMap functional-dependency research preview — discovery overlay</h1>"
        "<p>Complete 331-identity discovery universe. The productive 300-gene baseline remains authoritative; discovery-only identities are not promoted into it.</p>"
        f"<p>Coverage: {len(available)} available profiles; {len(unavailable)} unavailable profiles. Benchmark and holdout membership is not available in this portable overlay unless explicitly recorded.</p>"
        "<p>Rank delta = dependency-aware candidate rank minus baseline rank. Negative deltas move toward a lower numerical rank and are not biological validation. DepMap cell-line dependency is not clinical anti-PD-1 response evidence; broad dependency may reflect general essentiality, and cell lines do not reproduce the complete tumor microenvironment.</p>"
        "<h2>Baseline and DepMap overlay views</h2>" + table(discovery) +
        "<h2>Strongest upward rank movements</h2>" + table(upward) +
        "<h2>Strongest downward rank movements</h2>" + table(downward))
    (args.html_output_dir / "depmap_discovery_overlay.html").write_text(overlay_html, encoding="utf-8", newline="")
    (args.html_output_dir / "report_manifest.json").write_text(json.dumps({"discovery_count": len(evidence), "productive_baseline_count": len(productive), "human_review_required": True}, sort_keys=True) + "\n", encoding="utf-8")
    validate_publication_tree(args.cards_output_dir, bundle_limit=False)
    validate_publication_tree(args.html_output_dir, bundle_limit=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

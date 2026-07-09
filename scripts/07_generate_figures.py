#!/usr/bin/env python3

"""
Generate TargetIntel-IO summary figures.

The script uses an existing ranked-target CSV when available. If the input file
does not exist, it rebuilds the feature table and therapeutic-intent rankings.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from targetintel.feature_table import build_feature_table
from targetintel.intent_ranking import (
    build_intent_rankings,
    save_ranked_targets,
)
from targetintel.visualization import generate_summary_figures


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate TargetIntel-IO summary figures."
    )

    parser.add_argument(
        "--input",
        type=Path,
        default=Path("results/ranked_targets.csv"),
        help="Existing ranked-target CSV.",
    )

    parser.add_argument(
        "--outdir",
        type=Path,
        default=Path("examples/figures"),
        help="Output directory for figures.",
    )

    parser.add_argument(
        "--top-n",
        type=int,
        default=10,
        help="Number of top targets in score and rank-shift figures.",
    )

    parser.add_argument(
        "--heatmap-top-n-per-mode",
        type=int,
        default=5,
        help="Number of top targets collected from each mode for the heatmap.",
    )

    parser.add_argument(
        "--page-size",
        type=int,
        default=100,
        help="Open Targets records per API page when rebuilding data.",
    )

    parser.add_argument(
        "--max-pages",
        type=int,
        default=3,
        help="Maximum Open Targets API pages when rebuilding data.",
    )

    parser.add_argument(
        "--refresh",
        action="store_true",
        help="Refresh Open Targets data if the ranked CSV must be rebuilt.",
    )

    return parser.parse_args()


def load_or_build_ranked_targets(
    input_path: Path,
    page_size: int,
    max_pages: int,
    refresh: bool,
) -> pd.DataFrame:
    """
    Load an existing ranked table or rebuild it from the pipeline.
    """
    if input_path.exists():
        print(f"Loading ranked targets from: {input_path}")
        return pd.read_csv(input_path)

    print(
        f"Ranked target file not found at {input_path}. "
        "Rebuilding the table."
    )

    feature_df = build_feature_table(
        page_size=page_size,
        max_pages=max_pages,
        refresh=refresh,
    )

    ranked_df = build_intent_rankings(feature_df)

    save_ranked_targets(
        ranked_df,
        output_path=input_path,
    )

    return ranked_df


def main() -> None:
    args = parse_args()

    ranked_df = load_or_build_ranked_targets(
        input_path=args.input,
        page_size=args.page_size,
        max_pages=args.max_pages,
        refresh=args.refresh,
    )

    written_paths = generate_summary_figures(
        ranked_df,
        output_dir=args.outdir,
        top_n=args.top_n,
        heatmap_top_n_per_mode=args.heatmap_top_n_per_mode,
    )

    print()
    print(f"Generated {len(written_paths)} figures in: {args.outdir}")

    for path in written_paths:
        print(f"- {path}")


if __name__ == "__main__":
    main()

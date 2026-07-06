#!/usr/bin/env python3

"""
Generate TargetIntel-IO target hypothesis cards.

This script builds the feature table, scores and ranks targets, then writes
Markdown hypothesis cards for the union of top targets across therapeutic
intent modes.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from targetintel.feature_table import build_feature_table
from targetintel.hypothesis_cards import write_top_target_cards
from targetintel.intent_ranking import build_intent_rankings


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate TargetIntel-IO target hypothesis cards."
    )

    parser.add_argument(
        "--page-size",
        type=int,
        default=100,
        help="Number of Open Targets API records per page.",
    )

    parser.add_argument(
        "--max-pages",
        type=int,
        default=3,
        help="Maximum number of Open Targets API pages to fetch.",
    )

    parser.add_argument(
        "--refresh",
        action="store_true",
        help="Refresh cached Open Targets API data.",
    )

    parser.add_argument(
        "--top-n-per-mode",
        type=int,
        default=10,
        help="Generate cards for the top N targets in each therapeutic-intent mode.",
    )

    parser.add_argument(
        "--outdir",
        type=Path,
        default=Path("results/target_cards"),
        help="Output directory for Markdown target cards.",
    )

    return parser.parse_args()


def main() -> None:
    args = parse_args()

    feature_df = build_feature_table(
        page_size=args.page_size,
        max_pages=args.max_pages,
        refresh=args.refresh,
    )

    ranked_df = build_intent_rankings(feature_df)

    written_paths = write_top_target_cards(
        ranked_df,
        output_dir=args.outdir,
        top_n_per_mode=args.top_n_per_mode,
    )

    print(f"Generated {len(written_paths)} target cards in: {args.outdir}")

    for path in written_paths:
        print(f"- {path}")


if __name__ == "__main__":
    main()

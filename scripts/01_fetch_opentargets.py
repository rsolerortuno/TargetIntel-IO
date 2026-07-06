#!/usr/bin/env python3

"""
Fetch melanoma-associated targets from Open Targets.

This script creates the first baseline evidence table for TargetIntel-IO:
Open Targets melanoma disease-association scores.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from targetintel.opentargets import get_melanoma_associated_targets


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fetch melanoma-associated targets from Open Targets."
    )

    parser.add_argument(
        "--page-size",
        type=int,
        default=100,
        help="Number of targets per Open Targets API page.",
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
        help="Force refresh of Open Targets API cache.",
    )

    parser.add_argument(
        "--out",
        type=Path,
        default=Path("data/processed/opentargets_melanoma_targets.csv"),
        help="Output CSV path.",
    )

    return parser.parse_args()


def main() -> None:
    args = parse_args()

    df = get_melanoma_associated_targets(
        page_size=args.page_size,
        max_pages=args.max_pages,
        refresh=args.refresh,
    )

    args.out.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(args.out, index=False)

    print(f"Saved {len(df)} targets to: {args.out}")
    print(df.head(10)[["target_symbol", "opentargets_score"]].to_string(index=False))


if __name__ == "__main__":
    main()

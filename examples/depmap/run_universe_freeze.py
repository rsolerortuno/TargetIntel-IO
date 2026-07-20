#!/usr/bin/env python3
"""Freeze supplied benchmark, discovery, and indexed background universes offline."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
from targetintel.functional_dependency import freeze_universes


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--benchmark", required=True)
    parser.add_argument("--discovery-sources", required=True)
    parser.add_argument("--discovery-policy", required=True)
    parser.add_argument("--background-gene-index", required=True)
    parser.add_argument("--context", required=True)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()
    try:
        manifest = freeze_universes(Path(args.benchmark), Path(args.discovery_sources), Path(args.discovery_policy), Path(args.background_gene_index), json.loads(Path(args.context).read_text(encoding="utf-8")), Path(args.output_dir))
    except ValueError as error:
        parser.error(str(error))
    print(manifest.freeze_id)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Build descriptive dependency profiles from explicit Issue 502 artifacts."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from targetintel.functional_dependency import (
    DepMapModelContextDefinition, DepMapProfileError,
    FunctionalDependencyProfilePolicy, build_dependency_profiles,
    write_dependency_profile_artifacts,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ingestion-dir", required=True)
    parser.add_argument("--context", required=True)
    parser.add_argument("--policy", required=True)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()
    try:
        context = DepMapModelContextDefinition.from_dict(json.loads(Path(args.context).read_text(encoding="utf-8")))
        policy = FunctionalDependencyProfilePolicy.from_dict(json.loads(Path(args.policy).read_text(encoding="utf-8")))
        run, assignments = build_dependency_profiles(Path(args.ingestion_dir).resolve(), context, policy)
        write_dependency_profile_artifacts(Path(args.output_dir).resolve(), run, assignments)
    except (DepMapProfileError, ValueError) as error:
        parser.error(str(error))
    print(run.run_id)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

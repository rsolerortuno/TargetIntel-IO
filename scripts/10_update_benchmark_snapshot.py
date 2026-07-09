#!/usr/bin/env python3

"""
Create or update the committed TargetIntel-IO benchmark snapshot.

The script copies benchmark outputs from results/benchmark, creates a
machine-readable manifest with SHA-256 hashes, and generates the public
examples/benchmark/README.md summary.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import shutil
import subprocess
from pathlib import Path
from typing import Any


DEFAULT_SOURCE_DIR = Path("results/benchmark")
DEFAULT_OUTPUT_DIR = Path("examples/benchmark")
DEFAULT_BENCHMARK_CONFIG = Path("configs/benchmark_targets.yaml")
DEFAULT_RANKED_INPUT = Path(
    "results/benchmark/ranked_targets_benchmark_universe.csv"
)

RESULT_FILES = (
    "benchmark_predictions.csv",
    "benchmark_summary.csv",
    "benchmark_summary.json",
    "intent_metrics.csv",
    "role_confusion_matrix.csv",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Update the committed benchmark-result snapshot."
    )

    parser.add_argument(
        "--source-dir",
        type=Path,
        default=DEFAULT_SOURCE_DIR,
        help="Directory containing generated benchmark outputs.",
    )

    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Directory where the public snapshot will be written.",
    )

    parser.add_argument(
        "--benchmark-config",
        type=Path,
        default=DEFAULT_BENCHMARK_CONFIG,
        help="Benchmark configuration used to generate the snapshot.",
    )

    parser.add_argument(
        "--ranked-input",
        type=Path,
        default=DEFAULT_RANKED_INPUT,
        help="Ranked benchmark-universe input used for evaluation.",
    )

    return parser.parse_args()


def validate_inputs(
    source_dir: Path,
    benchmark_config: Path,
    ranked_input: Path,
) -> None:
    missing = [
        source_dir / filename
        for filename in RESULT_FILES
        if not (source_dir / filename).is_file()
    ]

    if missing:
        formatted = "\n".join(f"- {path}" for path in missing)
        raise FileNotFoundError(
            "Missing benchmark result files:\n"
            f"{formatted}"
        )

    if not benchmark_config.is_file():
        raise FileNotFoundError(
            f"Benchmark configuration not found: {benchmark_config}"
        )

    if not ranked_input.is_file():
        raise FileNotFoundError(
            f"Ranked benchmark input not found: {ranked_input}"
        )


def git_commit() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()

    with path.open("rb") as handle:
        for chunk in iter(
            lambda: handle.read(1024 * 1024),
            b"",
        ):
            digest.update(chunk)

    return digest.hexdigest()


def percentage(
    value: Any,
    digits: int = 1,
) -> str:
    if value is None:
        return "N/A"

    try:
        return f"{float(value) * 100:.{digits}f}%"
    except (TypeError, ValueError):
        return "N/A"


def integer(value: Any) -> str:
    if value is None:
        return "N/A"

    try:
        return str(int(float(value)))
    except (TypeError, ValueError):
        return "N/A"


def copy_result_files(
    source_dir: Path,
    output_dir: Path,
) -> list[Path]:
    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    copied: list[Path] = []

    for filename in RESULT_FILES:
        source = source_dir / filename
        destination = output_dir / filename

        shutil.copy2(
            source,
            destination,
        )

        copied.append(destination)

    return copied


def load_summary(
    output_dir: Path,
) -> dict[str, Any]:
    path = output_dir / "benchmark_summary.json"

    payload = json.loads(
        path.read_text(encoding="utf-8")
    )

    if not isinstance(payload, dict):
        raise ValueError(
            "benchmark_summary.json must contain a JSON object."
        )

    return payload


def load_intent_metrics(
    output_dir: Path,
) -> list[dict[str, str]]:
    path = output_dir / "intent_metrics.csv"

    with path.open(
        "r",
        encoding="utf-8",
        newline="",
    ) as handle:
        return list(csv.DictReader(handle))


def write_manifest(
    output_dir: Path,
    copied_files: list[Path],
    summary: dict[str, Any],
    benchmark_config: Path,
    ranked_input: Path,
) -> Path:
    manifest = {
        "benchmark_id": summary.get("benchmark_id"),
        "benchmark_version": summary.get(
            "benchmark_version"
        ),
        "validation_level": summary.get(
            "validation_level"
        ),
        "generated_from_commit": git_commit(),
        "benchmark_config": benchmark_config.as_posix(),
        "ranked_input": ranked_input.as_posix(),
        "files": {
            path.name: {
                "sha256": sha256_file(path),
                "size_bytes": path.stat().st_size,
            }
            for path in copied_files
        },
    }

    path = output_dir / "snapshot_manifest.json"

    path.write_text(
        json.dumps(
            manifest,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    return path


def build_intent_table(
    rows: list[dict[str, str]],
) -> list[str]:
    table_rows: list[str] = []

    for row in rows:
        table_rows.append(
            "| "
            + " | ".join(
                [
                    row.get("intent", "unknown"),
                    integer(
                        row.get("expected_target_count")
                    ),
                    percentage(
                        row.get(
                            "primary_intent_accuracy"
                        )
                    ),
                    percentage(
                        row.get(
                            "acceptable_intent_accuracy"
                        )
                    ),
                    percentage(
                        row.get("top_10_recall_all")
                    ),
                    percentage(
                        row.get("top_20_recall_all")
                    ),
                ]
            )
            + " |"
        )

    return table_rows


def write_snapshot_readme(
    output_dir: Path,
    summary: dict[str, Any],
    intent_rows: list[dict[str, str]],
) -> Path:
    commit = git_commit()

    lines = [
        "# Benchmark snapshot",
        "",
        (
            "This directory contains a versioned output snapshot of the "
            "TargetIntel-IO internal therapeutic-intent benchmark."
        ),
        "",
        (
            f"The snapshot was generated from repository commit `{commit}` "
            "using the curated 56-target benchmark in "
            "`configs/benchmark_targets.yaml`."
        ),
        "",
        "## Summary",
        "",
        "| Metric | Result |",
        "|---|---:|",
        (
            "| Benchmark targets | "
            f"{integer(summary.get('total_benchmark_targets'))} |"
        ),
        (
            "| Benchmark targets evaluated | "
            f"{integer(summary.get('covered_benchmark_targets'))} |"
        ),
        (
            "| Missing benchmark targets | "
            f"{integer(summary.get('missing_benchmark_targets'))} |"
        ),
        (
            "| TargetIntel evaluation coverage | "
            f"{percentage(summary.get('targetintel_evaluation_coverage'))} |"
        ),
        (
            "| Open Targets retrieved benchmark targets | "
            f"{integer(summary.get('opentargets_retrieved_benchmark_targets'))} |"
        ),
        (
            "| Open Targets top-300 retrieval coverage | "
            f"{percentage(summary.get('opentargets_retrieval_coverage'))} |"
        ),
        (
            "| Stable-role accuracy | "
            f"{percentage(summary.get('role_accuracy_covered'))} |"
        ),
        (
            "| Stable-role macro F1 | "
            f"{percentage(summary.get('role_macro_f1_covered'))} |"
        ),
        (
            "| Strict primary-intent accuracy | "
            f"{percentage(summary.get('primary_intent_accuracy_covered'))} |"
        ),
        (
            "| Strict primary-intent macro F1 | "
            f"{percentage(summary.get('primary_intent_macro_f1_covered'))} |"
        ),
        (
            "| Acceptable-intent accuracy | "
            f"{percentage(summary.get('acceptable_intent_accuracy_covered'))} |"
        ),
        (
            "| Cross-intent specificity | "
            f"{percentage(summary.get('cross_intent_specificity_covered'))} |"
        ),
        (
            "| Control not-prioritized rate | "
            f"{percentage(summary.get('control_not_prioritized_rate_covered'))} |"
        ),
        (
            "| Mean top-5 recall | "
            f"{percentage(summary.get('mean_mode_top_5_recall_covered'))} |"
        ),
        (
            "| Mean top-10 recall | "
            f"{percentage(summary.get('mean_mode_top_10_recall_covered'))} |"
        ),
        (
            "| Mean top-20 recall | "
            f"{percentage(summary.get('mean_mode_top_20_recall_covered'))} |"
        ),
        "",
        "## Results by therapeutic intent",
        "",
        (
            "| Intent | Expected targets | Primary-intent accuracy | "
            "Acceptable-intent accuracy | Top-10 recall | Top-20 recall |"
        ),
        "|---|---:|---:|---:|---:|---:|",
        *build_intent_table(intent_rows),
        "",
        "## Included files",
        "",
        "| File | Description |",
        "|---|---|",
        (
            "| `benchmark_predictions.csv` | Per-target expected and "
            "predicted roles, intents, scores, ranks, and correctness flags |"
        ),
        (
            "| `benchmark_summary.csv` | Benchmark-level metrics in "
            "tabular format |"
        ),
        (
            "| `benchmark_summary.json` | Machine-readable benchmark-level "
            "metrics |"
        ),
        (
            "| `intent_metrics.csv` | Metrics separated by therapeutic "
            "intent |"
        ),
        (
            "| `role_confusion_matrix.csv` | Stable-role classification "
            "confusion matrix |"
        ),
        (
            "| `snapshot_manifest.json` | Source commit, file hashes, and "
            "snapshot metadata |"
        ),
        "",
        "## Interpretation",
        "",
        (
            "This benchmark is an internal, rule-based sanity validation. "
            "It tests whether the framework behaves consistently across "
            "curated biological and translational examples."
        ),
        "",
        (
            "It is not an independent clinical gold standard and does not "
            "demonstrate therapeutic efficacy, biomarker qualification, or "
            "prospective predictive performance."
        ),
        "",
        (
            "The augmented benchmark universe deliberately includes curated "
            "targets that were not retrieved among the top 300 Open Targets "
            "melanoma associations."
        ),
        "",
        "This keeps two concepts separate:",
        "",
        "- Open Targets retrieval coverage;",
        "- TargetIntel-IO rule-evaluation coverage.",
        "",
        "## Reproduce the snapshot",
        "",
        "Build the augmented benchmark universe:",
        "",
        "~~~bash",
        "python scripts/09_build_benchmark_universe.py \\",
        "  --page-size 100 \\",
        "  --max-pages 3",
        "~~~",
        "",
        "Run the benchmark:",
        "",
        "~~~bash",
        "python scripts/08_run_benchmark.py \\",
        (
            "  --input "
            "results/benchmark/ranked_targets_benchmark_universe.csv \\"
        ),
        "  --config configs/benchmark_targets.yaml \\",
        "  --outdir results/benchmark \\",
        "  --show-missing \\",
        "  --show-errors",
        "~~~",
        "",
        "Update this committed snapshot:",
        "",
        "~~~bash",
        "python scripts/10_update_benchmark_snapshot.py",
        "~~~",
    ]

    path = output_dir / "README.md"

    path.write_text(
        "\n".join(lines).rstrip() + "\n",
        encoding="utf-8",
    )

    return path


def main() -> None:
    args = parse_args()

    validate_inputs(
        source_dir=args.source_dir,
        benchmark_config=args.benchmark_config,
        ranked_input=args.ranked_input,
    )

    copied_files = copy_result_files(
        source_dir=args.source_dir,
        output_dir=args.output_dir,
    )

    summary = load_summary(args.output_dir)

    intent_rows = load_intent_metrics(
        args.output_dir
    )

    manifest_path = write_manifest(
        output_dir=args.output_dir,
        copied_files=copied_files,
        summary=summary,
        benchmark_config=args.benchmark_config,
        ranked_input=args.ranked_input,
    )

    readme_path = write_snapshot_readme(
        output_dir=args.output_dir,
        summary=summary,
        intent_rows=intent_rows,
    )

    print("Benchmark snapshot updated:")
    for path in [
        *copied_files,
        manifest_path,
        readme_path,
    ]:
        print(f"- {path}")


if __name__ == "__main__":
    main()

"""
Visualization utilities for TargetIntel-IO.

This module generates static figures from the therapeutic-intent-aware
ranked target table.

The figures are intended for transparent result communication, portfolio
presentation, and README documentation.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


DEFAULT_FIGURE_DIR = Path("examples/figures")


MODE_METADATA = {
    "antibody_io": {
        "label": "Antibody / IO-combination",
        "score_column": "antibody_io_final_score",
        "rank_column": "antibody_io_rank",
        "priority_column": "antibody_io_priority",
        "shift_column": "antibody_io_rank_shift_vs_opentargets",
    },
    "biomarker": {
        "label": "Resistance biomarker",
        "score_column": "biomarker_final_score",
        "rank_column": "biomarker_rank",
        "priority_column": "biomarker_priority",
        "shift_column": "biomarker_rank_shift_vs_opentargets",
    },
    "small_molecule": {
        "label": "Tumor-intrinsic / small molecule",
        "score_column": "small_molecule_final_score",
        "rank_column": "small_molecule_rank",
        "priority_column": "small_molecule_priority",
        "shift_column": "small_molecule_rank_shift_vs_opentargets",
    },
}


def _safe_str(value: Any) -> str:
    """Convert a potentially missing value into a clean string."""
    if value is None:
        return ""

    try:
        if pd.isna(value):
            return ""
    except TypeError:
        pass

    return str(value).strip()


def _ensure_columns(
    df: pd.DataFrame,
    required_columns: list[str],
) -> None:
    """Raise an informative error when required columns are missing."""
    missing_columns = [
        column for column in required_columns if column not in df.columns
    ]

    if missing_columns:
        raise KeyError(
            "The ranked target table is missing required columns: "
            f"{missing_columns}"
        )


def _prepare_output_path(output_path: str | Path) -> Path:
    """Create the parent directory for a figure output path."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    return output_path


def get_top_targets(
    ranked_df: pd.DataFrame,
    mode: str,
    top_n: int = 10,
    prioritized_only: bool = True,
) -> pd.DataFrame:
    """
    Select the top targets for one therapeutic-intent mode.

    Parameters
    ----------
    ranked_df:
        Ranked TargetIntel-IO dataframe.
    mode:
        One of antibody_io, biomarker, or small_molecule.
    top_n:
        Maximum number of targets to return.
    prioritized_only:
        If True, remove targets labelled as not prioritized.
    """
    if mode not in MODE_METADATA:
        raise ValueError(
            f"Unknown mode: {mode}. "
            f"Expected one of: {list(MODE_METADATA)}"
        )

    metadata = MODE_METADATA[mode]

    required_columns = [
        "target_symbol",
        metadata["score_column"],
        metadata["rank_column"],
        metadata["priority_column"],
    ]

    _ensure_columns(ranked_df, required_columns)

    subset = ranked_df.copy()

    subset[metadata["score_column"]] = pd.to_numeric(
        subset[metadata["score_column"]],
        errors="coerce",
    ).fillna(0.0)

    subset[metadata["rank_column"]] = pd.to_numeric(
        subset[metadata["rank_column"]],
        errors="coerce",
    )

    if prioritized_only:
        priority_values = (
            subset[metadata["priority_column"]]
            .astype(str)
            .str.strip()
            .str.lower()
        )

        subset = subset[
            priority_values.ne("not prioritized")
            & subset[metadata["score_column"]].gt(0)
        ]

    subset = subset.sort_values(
        by=[
            metadata["rank_column"],
            metadata["score_column"],
            "target_symbol",
        ],
        ascending=[True, False, True],
    )

    return subset.head(top_n).copy()


def plot_top_targets(
    ranked_df: pd.DataFrame,
    mode: str,
    output_path: str | Path,
    top_n: int = 10,
) -> Path:
    """
    Plot the top targets by final therapeutic-intent score.
    """
    metadata = MODE_METADATA[mode]

    subset = get_top_targets(
        ranked_df,
        mode=mode,
        top_n=top_n,
        prioritized_only=True,
    )

    if subset.empty:
        raise ValueError(f"No prioritized targets available for mode: {mode}")

    output_path = _prepare_output_path(output_path)

    score_column = metadata["score_column"]

    fig_height = max(5.0, 0.55 * len(subset))
    fig, ax = plt.subplots(figsize=(10, fig_height))

    bars = ax.barh(
        subset["target_symbol"],
        subset[score_column],
    )

    ax.invert_yaxis()
    ax.set_xlim(0, 1)
    ax.set_xlabel("TargetIntel-IO final score")
    ax.set_ylabel("Target")
    ax.set_title(f"Top {metadata['label']} targets")

    for bar, score in zip(bars, subset[score_column]):
        ax.text(
            min(float(score) + 0.015, 0.97),
            bar.get_y() + bar.get_height() / 2,
            f"{float(score):.2f}",
            va="center",
        )

    fig.tight_layout()
    fig.savefig(output_path, dpi=220, bbox_inches="tight")
    plt.close(fig)

    return output_path


def plot_rank_shift(
    ranked_df: pd.DataFrame,
    mode: str,
    output_path: str | Path,
    top_n: int = 10,
) -> Path:
    """
    Plot rank changes relative to the Open Targets baseline.

    Positive values mean that TargetIntel-IO moved the target upward for the
    selected therapeutic intent.
    """
    metadata = MODE_METADATA[mode]

    required_columns = [
        "target_symbol",
        metadata["rank_column"],
        metadata["priority_column"],
        metadata["shift_column"],
    ]

    _ensure_columns(ranked_df, required_columns)

    subset = get_top_targets(
        ranked_df,
        mode=mode,
        top_n=top_n,
        prioritized_only=True,
    )

    shift_column = metadata["shift_column"]

    subset[shift_column] = pd.to_numeric(
        subset[shift_column],
        errors="coerce",
    ).fillna(0)

    output_path = _prepare_output_path(output_path)

    fig_height = max(5.0, 0.55 * len(subset))
    fig, ax = plt.subplots(figsize=(10, fig_height))

    bars = ax.barh(
        subset["target_symbol"],
        subset[shift_column],
    )

    ax.invert_yaxis()
    ax.axvline(0, linewidth=1)
    ax.set_xlabel("Rank shift versus Open Targets")
    ax.set_ylabel("Target")
    ax.set_title(
        f"Rank shifts for top {metadata['label']} targets"
    )

    for bar, shift in zip(bars, subset[shift_column]):
        shift = int(shift)

        if shift >= 0:
            text_x = shift + 1
            horizontal_alignment = "left"
        else:
            text_x = shift - 1
            horizontal_alignment = "right"

        ax.text(
            text_x,
            bar.get_y() + bar.get_height() / 2,
            f"{shift:+d}",
            va="center",
            ha=horizontal_alignment,
        )

    fig.tight_layout()
    fig.savefig(output_path, dpi=220, bbox_inches="tight")
    plt.close(fig)

    return output_path


def _collect_heatmap_targets(
    ranked_df: pd.DataFrame,
    top_n_per_mode: int,
) -> list[str]:
    """
    Collect the union of top targets across all therapeutic-intent modes.
    """
    selected_symbols: list[str] = []
    seen_symbols: set[str] = set()

    for mode in MODE_METADATA:
        subset = get_top_targets(
            ranked_df,
            mode=mode,
            top_n=top_n_per_mode,
            prioritized_only=True,
        )

        for symbol in subset["target_symbol"]:
            symbol = _safe_str(symbol)

            if symbol and symbol not in seen_symbols:
                selected_symbols.append(symbol)
                seen_symbols.add(symbol)

    return selected_symbols


def plot_intent_score_heatmap(
    ranked_df: pd.DataFrame,
    output_path: str | Path,
    top_n_per_mode: int = 5,
) -> Path:
    """
    Plot therapeutic-intent scores for the union of top targets.

    This figure demonstrates that the same target can have different priority
    depending on the therapeutic question.
    """
    score_columns = [
        MODE_METADATA["antibody_io"]["score_column"],
        MODE_METADATA["biomarker"]["score_column"],
        MODE_METADATA["small_molecule"]["score_column"],
    ]

    _ensure_columns(
        ranked_df,
        ["target_symbol"] + score_columns,
    )

    selected_symbols = _collect_heatmap_targets(
        ranked_df,
        top_n_per_mode=top_n_per_mode,
    )

    if not selected_symbols:
        raise ValueError("No targets were selected for the heatmap.")

    matrix_df = (
        ranked_df[
            ranked_df["target_symbol"].isin(selected_symbols)
        ]
        .drop_duplicates(subset=["target_symbol"])
        .set_index("target_symbol")
        .reindex(selected_symbols)[score_columns]
        .apply(pd.to_numeric, errors="coerce")
        .fillna(0.0)
    )

    matrix_df["maximum_intent_score"] = matrix_df.max(axis=1)

    matrix_df = matrix_df.sort_values(
        "maximum_intent_score",
        ascending=False,
    ).drop(columns="maximum_intent_score")

    matrix = matrix_df.to_numpy(dtype=float)

    output_path = _prepare_output_path(output_path)

    fig_height = max(6.0, 0.48 * len(matrix_df))
    fig, ax = plt.subplots(figsize=(9, fig_height))

    image = ax.imshow(
        matrix,
        aspect="auto",
        vmin=0,
        vmax=1,
    )

    ax.set_xticks(np.arange(len(score_columns)))
    ax.set_xticklabels(
        [
            "Antibody / IO",
            "Biomarker",
            "Small molecule",
        ]
    )

    ax.set_yticks(np.arange(len(matrix_df.index)))
    ax.set_yticklabels(matrix_df.index)

    ax.set_xlabel("Therapeutic intent")
    ax.set_ylabel("Target")
    ax.set_title("TargetIntel-IO therapeutic-intent score matrix")

    for row_index in range(matrix.shape[0]):
        for column_index in range(matrix.shape[1]):
            ax.text(
                column_index,
                row_index,
                f"{matrix[row_index, column_index]:.2f}",
                ha="center",
                va="center",
            )

    colorbar = fig.colorbar(image, ax=ax)
    colorbar.set_label("Final score")

    fig.tight_layout()
    fig.savefig(output_path, dpi=220, bbox_inches="tight")
    plt.close(fig)

    return output_path


def generate_summary_figures(
    ranked_df: pd.DataFrame,
    output_dir: str | Path = DEFAULT_FIGURE_DIR,
    top_n: int = 10,
    heatmap_top_n_per_mode: int = 5,
) -> list[Path]:
    """
    Generate all standard TargetIntel-IO portfolio figures.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    written_paths: list[Path] = []

    for mode in MODE_METADATA:
        written_paths.append(
            plot_top_targets(
                ranked_df,
                mode=mode,
                output_path=output_dir / f"top_{mode}.png",
                top_n=top_n,
            )
        )

        written_paths.append(
            plot_rank_shift(
                ranked_df,
                mode=mode,
                output_path=output_dir / f"rank_shift_{mode}.png",
                top_n=top_n,
            )
        )

    written_paths.append(
        plot_intent_score_heatmap(
            ranked_df,
            output_path=output_dir / "intent_score_heatmap.png",
            top_n_per_mode=heatmap_top_n_per_mode,
        )
    )

    return written_paths

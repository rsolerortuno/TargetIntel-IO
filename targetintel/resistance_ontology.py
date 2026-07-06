"""
Resistance ontology utilities for TargetIntel-IO.

This module reads the curated anti-PD-1 resistance-axis ontology from
configs/resistance_axes.yaml and maps candidate genes to one or more
biological resistance programs.

The goal is not to infer causal biology automatically, but to provide a
transparent, auditable rule-based mapping between candidate targets and
curated immuno-oncology resistance axes.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd
import yaml


DEFAULT_ONTOLOGY_PATH = Path("configs/resistance_axes.yaml")


def load_resistance_axes(
    ontology_path: str | Path = DEFAULT_ONTOLOGY_PATH,
) -> dict[str, dict[str, Any]]:
    """
    Load the anti-PD-1 resistance-axis ontology from a YAML file.

    Parameters
    ----------
    ontology_path:
        Path to the resistance-axis YAML configuration file.

    Returns
    -------
    dict
        Dictionary where each key is a resistance-axis ID and each value
        contains labels, descriptions, example genes, expected roles,
        therapeutic direction, modality preferences, and evidence notes.
    """
    ontology_path = Path(ontology_path)

    if not ontology_path.exists():
        raise FileNotFoundError(f"Resistance ontology not found: {ontology_path}")

    with ontology_path.open("r", encoding="utf-8") as handle:
        axes = yaml.safe_load(handle)

    if not isinstance(axes, dict):
        raise ValueError(
            "Resistance ontology must be a YAML dictionary with one entry per axis."
        )

    return axes


def build_gene_axis_index(
    axes: dict[str, dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    """
    Build a gene-to-resistance-axis lookup table.

    A gene may map to more than one axis. For example, CTLA4 may appear in
    checkpoint redundancy and Treg-mediated suppression.
    """
    gene_index: dict[str, list[dict[str, Any]]] = {}

    for axis_id, axis_info in axes.items():
        genes = axis_info.get("example_genes", [])

        for gene in genes:
            gene_symbol = str(gene).upper()

            gene_index.setdefault(gene_symbol, []).append(
                {
                    "axis_id": axis_id,
                    "axis_label": axis_info.get("label", axis_id),
                    "description": axis_info.get("description", ""),
                    "expected_role": axis_info.get("expected_role", "unclear"),
                    "therapeutic_direction": axis_info.get(
                        "therapeutic_direction", "unclear"
                    ),
                    "preferred_modalities": axis_info.get("preferred_modalities", []),
                    "evidence_for": axis_info.get("evidence_for", []),
                    "evidence_against": axis_info.get("evidence_against", []),
                }
            )

    return gene_index


def annotate_gene(
    gene_symbol: str,
    gene_axis_index: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    """
    Annotate a single gene using the curated resistance-axis ontology.

    Parameters
    ----------
    gene_symbol:
        HGNC-style gene symbol.
    gene_axis_index:
        Gene-to-axis lookup created by build_gene_axis_index().

    Returns
    -------
    dict
        Dictionary with matched resistance axes, expected translational role,
        therapeutic direction, modality preferences, and evidence notes.
    """
    gene_symbol = str(gene_symbol).upper()
    matches = gene_axis_index.get(gene_symbol, [])

    if not matches:
        return {
            "target_symbol": gene_symbol,
            "resistance_axis": "unmapped",
            "matched_resistance_programs": "",
            "matched_signature_genes": "",
            "resistance_axis_score": 0.0,
            "resistance_axis_confidence": "none",
            "expected_role_from_axis": "unclear / low-confidence candidate",
            "therapeutic_direction_from_axis": "unclear",
            "preferred_modalities_from_axis": "",
            "axis_evidence_for": "",
            "axis_evidence_against": "",
        }

    axis_ids = [match["axis_id"] for match in matches]
    axis_labels = [match["axis_label"] for match in matches]

    expected_roles = sorted(
        {
            match["expected_role"]
            for match in matches
            if match.get("expected_role")
        }
    )

    therapeutic_directions = sorted(
        {
            match["therapeutic_direction"]
            for match in matches
            if match.get("therapeutic_direction")
        }
    )

    preferred_modalities = sorted(
        {
            modality
            for match in matches
            for modality in match.get("preferred_modalities", [])
        }
    )

    evidence_for = sorted(
        {
            item
            for match in matches
            for item in match.get("evidence_for", [])
        }
    )

    evidence_against = sorted(
        {
            item
            for match in matches
            for item in match.get("evidence_against", [])
        }
    )

    # Simple transparent score for MVP:
    # 1.0 if directly curated in at least one resistance axis.
    # Multi-axis genes receive higher confidence but are capped at 1.0.
    resistance_axis_score = min(1.0, 0.75 + 0.15 * (len(matches) - 1))

    if len(matches) >= 2:
        confidence = "high"
    else:
        confidence = "medium"

    return {
        "target_symbol": gene_symbol,
        "resistance_axis": "; ".join(axis_ids),
        "matched_resistance_programs": "; ".join(axis_labels),
        "matched_signature_genes": gene_symbol,
        "resistance_axis_score": resistance_axis_score,
        "resistance_axis_confidence": confidence,
        "expected_role_from_axis": "; ".join(expected_roles),
        "therapeutic_direction_from_axis": "; ".join(therapeutic_directions),
        "preferred_modalities_from_axis": "; ".join(preferred_modalities),
        "axis_evidence_for": " | ".join(evidence_for),
        "axis_evidence_against": " | ".join(evidence_against),
    }


def annotate_dataframe(
    df: pd.DataFrame,
    gene_column: str = "target_symbol",
    ontology_path: str | Path = DEFAULT_ONTOLOGY_PATH,
) -> pd.DataFrame:
    """
    Annotate a dataframe of candidate targets with resistance-axis information.

    Parameters
    ----------
    df:
        Input dataframe containing candidate genes.
    gene_column:
        Column containing gene symbols.
    ontology_path:
        Path to resistance_axes.yaml.

    Returns
    -------
    pandas.DataFrame
        Original dataframe with resistance-axis annotation columns appended.
    """
    if gene_column not in df.columns:
        raise KeyError(f"Column not found in dataframe: {gene_column}")

    axes = load_resistance_axes(ontology_path)
    gene_axis_index = build_gene_axis_index(axes)

    annotations = [
        annotate_gene(gene_symbol, gene_axis_index)
        for gene_symbol in df[gene_column]
    ]

    annotation_df = pd.DataFrame(annotations)

    # Avoid duplicating the gene column if input already contains it.
    annotation_df = annotation_df.drop(columns=["target_symbol"], errors="ignore")

    return pd.concat([df.reset_index(drop=True), annotation_df], axis=1)

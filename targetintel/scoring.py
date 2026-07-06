"""
Therapeutic-intent scoring for TargetIntel-IO.

This module applies configurable YAML scoring profiles to the TargetIntel-IO
feature table.

Each scoring profile answers a different translational question:

- antibody_io:
    Which candidates are best for antibody / IO-combination strategies?

- biomarker:
    Which candidates are best interpreted as resistance biomarkers or
    patient-stratification markers?

- small_molecule:
    Which candidates are best for tumor-intrinsic or small-molecule intervention?

The scoring is intentionally transparent, rule-based, and configurable.
Scores are not probabilities and do not claim clinical validity.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd
import yaml


DEFAULT_SCORING_CONFIGS = {
    "antibody_io": Path("configs/scoring_antibody_io.yaml"),
    "biomarker": Path("configs/scoring_biomarker.yaml"),
    "small_molecule": Path("configs/scoring_small_molecule.yaml"),
}


DEFAULT_MODALITY_WEIGHTS = {
    "antibody_io": {
        "antibody_fit": 0.45,
        "io_combination_fit": 0.45,
        "biomarker_fit": 0.05,
        "small_molecule_fit": 0.05,
    },
    "biomarker": {
        "biomarker_fit": 0.70,
        "io_combination_fit": 0.10,
        "antibody_fit": 0.10,
        "small_molecule_fit": 0.10,
    },
    "small_molecule": {
        "small_molecule_fit": 0.70,
        "biomarker_fit": 0.15,
        "io_combination_fit": 0.10,
        "antibody_fit": 0.05,
    },
}


REQUIRED_CONFIG_SECTIONS = [
    "scoring_profile",
    "weights",
    "role_scores",
    "modality_scores",
    "confidence_scores",
    "penalties",
]


def load_scoring_config(config_path: str | Path) -> dict[str, Any]:
    """
    Load one therapeutic-intent scoring configuration from YAML.

    Parameters
    ----------
    config_path:
        Path to YAML scoring configuration.

    Returns
    -------
    dict
        Parsed scoring configuration.
    """
    config_path = Path(config_path)

    if not config_path.exists():
        raise FileNotFoundError(f"Scoring config not found: {config_path}")

    with config_path.open("r", encoding="utf-8") as handle:
        config = yaml.safe_load(handle)

    if not isinstance(config, dict):
        raise ValueError(f"Scoring config must be a YAML dictionary: {config_path}")

    missing_sections = [
        section for section in REQUIRED_CONFIG_SECTIONS if section not in config
    ]

    if missing_sections:
        raise ValueError(
            f"Scoring config {config_path} is missing required sections: "
            f"{missing_sections}"
        )

    if "id" not in config["scoring_profile"]:
        raise ValueError(
            f"Scoring config {config_path} must define scoring_profile.id"
        )

    return config


def _safe_str(value: Any) -> str:
    """Convert a value to a clean string."""
    if value is None:
        return ""

    try:
        if pd.isna(value):
            return ""
    except TypeError:
        pass

    return str(value).strip()


def _safe_float(value: Any, default: float = 0.0) -> float:
    """Convert a value to float safely."""
    if value is None:
        return default

    try:
        if pd.isna(value):
            return default
    except TypeError:
        pass

    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _safe_bool(value: Any) -> bool:
    """Convert common truthy values to bool."""
    if isinstance(value, bool):
        return value

    if value is None:
        return False

    try:
        if pd.isna(value):
            return False
    except TypeError:
        pass

    return str(value).strip().lower() in {"true", "1", "yes", "y"}


def _clip01(value: float) -> float:
    """Clip a score to the [0, 1] interval."""
    return max(0.0, min(1.0, value))


def _lookup_score(
    value: Any,
    score_map: dict[str, float],
    default: float = 0.0,
) -> float:
    """
    Look up a numeric score from a mapping.

    Matching is case-insensitive and robust to extra whitespace.
    """
    value_str = _safe_str(value)

    if value_str in score_map:
        return float(score_map[value_str])

    lower_score_map = {
        str(key).strip().lower(): float(score)
        for key, score in score_map.items()
    }

    return lower_score_map.get(value_str.lower(), default)


def calculate_role_fit_score(
    row: pd.Series,
    config: dict[str, Any],
) -> float:
    """
    Calculate how well the target role fits the therapeutic intent.
    """
    role = row.get("role_classification", "")
    role_scores = config.get("role_scores", {})

    return _clip01(_lookup_score(role, role_scores, default=0.0))


def calculate_modality_fit_score(
    row: pd.Series,
    config: dict[str, Any],
) -> float:
    """
    Calculate the profile-specific modality-fit score.

    The YAML maps modality labels such as 'high', 'medium', 'low', or 'unclear'
    into numeric scores. This function then combines several modality columns
    using profile-specific modality weights.
    """
    profile_id = config["scoring_profile"]["id"]

    modality_scores = config.get("modality_scores", {})
    modality_weights = config.get(
        "modality_weights",
        DEFAULT_MODALITY_WEIGHTS.get(profile_id, {}),
    )

    if not modality_weights:
        return 0.0

    weighted_sum = 0.0
    weight_sum = 0.0

    for modality_column, weight in modality_weights.items():
        if modality_column not in modality_scores:
            continue

        fit_label = row.get(modality_column, "unclear")
        fit_score_map = modality_scores[modality_column]
        fit_score = _lookup_score(fit_label, fit_score_map, default=0.0)

        weighted_sum += fit_score * float(weight)
        weight_sum += float(weight)

    if weight_sum == 0:
        return 0.0

    return _clip01(weighted_sum / weight_sum)


def calculate_confidence_score(
    row: pd.Series,
    config: dict[str, Any],
) -> float:
    """
    Convert confidence level into a numeric score.
    """
    confidence_scores = config.get("confidence_scores", {})
    confidence_level = row.get("confidence_level", "")

    return _clip01(
        _lookup_score(confidence_level, confidence_scores, default=0.0)
    )


def calculate_evidence_balance_score(row: pd.Series) -> float:
    """
    Convert contradiction score into a positive evidence-balance score.

    contradiction_score:
        0 means little opposing evidence.
        1 means strong caution / contradiction.

    evidence_balance_score:
        1 means favorable evidence balance.
        0 means unfavorable evidence balance.
    """
    contradiction_score = _safe_float(row.get("contradiction_score"), default=0.0)

    return _clip01(1.0 - contradiction_score)


def calculate_novelty_or_crowding_score(row: pd.Series) -> float:
    """
    Placeholder novelty/crowding score.

    The current MVP does not yet include PubMed or ClinicalTrials counts.
    Until the evidence-density module is implemented, this returns a neutral
    value unless a novelty/crowding column already exists.
    """
    if "novelty_or_crowding_score" in row.index:
        return _clip01(
            _safe_float(row.get("novelty_or_crowding_score"), default=0.5)
        )

    if "crowding_score" in row.index:
        crowding_score = _safe_float(row.get("crowding_score"), default=0.5)
        return _clip01(1.0 - crowding_score)

    return 0.5


def calculate_standard_penalty(
    row: pd.Series,
    config: dict[str, Any],
) -> float:
    """
    Calculate standard additive penalties.

    Penalties in the YAML should normally be negative values.
    """
    penalties = config.get("penalties", {})

    penalty = 0.0

    if _safe_bool(row.get("poor_direct_target_flag", False)):
        penalty += float(penalties.get("poor_direct_target_flag", 0.0))

    contradiction_score = _safe_float(row.get("contradiction_score"), default=0.0)

    if contradiction_score >= 0.6:
        penalty += float(penalties.get("high_contradiction_score", 0.0))

    resistance_axis = _safe_str(row.get("resistance_axis", "")).lower()

    if resistance_axis in {"", "unmapped", "nan"}:
        penalty += float(penalties.get("unmapped_resistance_axis", 0.0))

    return penalty


def calculate_intent_mismatch_penalty(
    row: pd.Series,
    config: dict[str, Any],
) -> float:
    """
    Apply explicit penalties for roles that do not fit the scoring intent.

    Example:
    - In antibody_io mode, tumor-intrinsic small-molecule drivers should be
      penalized.
    - In small_molecule mode, antibody IO-combination targets and biomarker-only
      candidates should be penalized.
    """
    role = _safe_str(row.get("role_classification", ""))
    intent_mismatch_penalties = config.get("intent_mismatch_penalties", {})

    if not intent_mismatch_penalties:
        return 0.0

    if role in intent_mismatch_penalties:
        return float(intent_mismatch_penalties[role])

    lower_penalties = {
        str(key).strip().lower(): float(value)
        for key, value in intent_mismatch_penalties.items()
    }

    return lower_penalties.get(role.lower(), 0.0)


def calculate_total_penalty(
    row: pd.Series,
    config: dict[str, Any],
) -> float:
    """
    Calculate total additive penalty for one row.
    """
    standard_penalty = calculate_standard_penalty(row, config)
    intent_mismatch_penalty = calculate_intent_mismatch_penalty(row, config)

    return standard_penalty + intent_mismatch_penalty


def score_row(
    row: pd.Series,
    config: dict[str, Any],
) -> dict[str, float]:
    """
    Score one target for one therapeutic-intent profile.

    Returns component scores plus the final score.
    """
    weights = config["weights"]

    opentargets_component_score = _clip01(
        _safe_float(row.get("opentargets_score"), default=0.0)
    )

    resistance_axis_component_score = _clip01(
        _safe_float(row.get("resistance_axis_score"), default=0.0)
    )

    role_fit_component_score = calculate_role_fit_score(row, config)

    modality_fit_component_score = calculate_modality_fit_score(row, config)

    confidence_component_score = calculate_confidence_score(row, config)

    evidence_balance_component_score = calculate_evidence_balance_score(row)

    novelty_or_crowding_component_score = calculate_novelty_or_crowding_score(row)

    weighted_score = (
        weights.get("opentargets_score", 0.0) * opentargets_component_score
        + weights.get("resistance_axis_score", 0.0)
        * resistance_axis_component_score
        + weights.get("role_fit_score", 0.0) * role_fit_component_score
        + weights.get("modality_fit_score", 0.0) * modality_fit_component_score
        + weights.get("confidence_score", 0.0) * confidence_component_score
        + weights.get("evidence_balance_score", 0.0)
        * evidence_balance_component_score
        + weights.get("novelty_or_crowding_score", 0.0)
        * novelty_or_crowding_component_score
    )

    standard_penalty_score = calculate_standard_penalty(row, config)
    intent_mismatch_penalty_score = calculate_intent_mismatch_penalty(row, config)
    total_penalty_score = standard_penalty_score + intent_mismatch_penalty_score

    final_score = _clip01(weighted_score + total_penalty_score)

    return {
        "opentargets_component_score": round(opentargets_component_score, 4),
        "resistance_axis_component_score": round(
            resistance_axis_component_score, 4
        ),
        "role_fit_component_score": round(role_fit_component_score, 4),
        "modality_fit_component_score": round(modality_fit_component_score, 4),
        "confidence_component_score": round(confidence_component_score, 4),
        "evidence_balance_component_score": round(
            evidence_balance_component_score, 4
        ),
        "novelty_or_crowding_component_score": round(
            novelty_or_crowding_component_score, 4
        ),
        "weighted_score_before_penalty": round(weighted_score, 4),
        "standard_penalty_score": round(standard_penalty_score, 4),
        "intent_mismatch_penalty_score": round(
            intent_mismatch_penalty_score, 4
        ),
        "total_penalty_score": round(total_penalty_score, 4),
        "final_score": round(final_score, 4),
    }


def score_dataframe_with_config(
    df: pd.DataFrame,
    config: dict[str, Any],
) -> pd.DataFrame:
    """
    Apply one scoring profile to a dataframe.

    Adds profile-specific component columns and the profile-specific final score.
    """
    df = df.copy()
    profile_id = config["scoring_profile"]["id"]

    scored_rows = []

    for _, row in df.iterrows():
        scored_rows.append(score_row(row, config))

    score_df = pd.DataFrame(scored_rows)

    score_df = score_df.rename(
        columns={
            column: f"{profile_id}_{column}"
            for column in score_df.columns
        }
    )

    return pd.concat(
        [df.reset_index(drop=True), score_df.reset_index(drop=True)],
        axis=1,
    )


def score_dataframe(
    df: pd.DataFrame,
    config_path: str | Path,
) -> pd.DataFrame:
    """
    Load one YAML scoring profile and apply it to a dataframe.
    """
    config = load_scoring_config(config_path)

    return score_dataframe_with_config(df, config)


def score_all_profiles(
    df: pd.DataFrame,
    config_paths: dict[str, str | Path] | None = None,
) -> pd.DataFrame:
    """
    Apply all therapeutic-intent scoring profiles to a dataframe.

    Parameters
    ----------
    df:
        Feature table produced by targetintel.feature_table.
    config_paths:
        Optional dictionary of profile_id -> YAML config path.

    Returns
    -------
    pandas.DataFrame
        DataFrame with score columns for all therapeutic-intent profiles.
    """
    scored_df = df.copy()

    if config_paths is None:
        config_paths = DEFAULT_SCORING_CONFIGS

    for _, config_path in config_paths.items():
        config = load_scoring_config(config_path)
        scored_df = score_dataframe_with_config(scored_df, config)

    return scored_df

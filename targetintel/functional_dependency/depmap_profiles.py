"""Deterministic, descriptive profiles from Issue 502 ingestion artifacts.

This module deliberately consumes derived TSV/JSON artifacts only.  It makes
no remote calls and does not interact with target selection or prioritization.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass
from hashlib import sha256
import json
import math
from pathlib import Path
from typing import Any, Mapping

from .depmap_models import _forbidden_nested, _freeze, _identity, _text, _thaw, canonical_json


CONTEXT_FORMAT_VERSION = "v0.5.0"
POLICY_FORMAT_VERSION = "v0.5.0"
PROFILE_FORMAT_VERSION = "v0.5.0"
RUN_FORMAT_VERSION = "v0.5.0"


class DepMapProfileError(ValueError):
    """Sanitized profile-input or calculation error."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise DepMapProfileError(message)


def _safe(value: Any) -> None:
    _require(not _forbidden_nested(value), "profile contract contains credentials or hidden reasoning")


def _sorted_values(values: Mapping[str, Any] | None) -> dict[str, tuple[str, ...]]:
    if values is None:
        return {}
    _require(isinstance(values, Mapping), "accepted values must be a mapping")
    result = {}
    for key, item in values.items():
        _require(_text(key) and isinstance(item, (list, tuple)) and item, "context fields require non-empty exact values")
        exact = tuple(sorted({str(value) for value in item}))
        _require(all(_text(value) for value in exact), "context values must be non-empty")
        result[str(key)] = exact
    return dict(sorted(result.items()))


@dataclass(frozen=True)
class DepMapModelContextDefinition:
    context_definition_format_version: str
    context_name: str
    context_version: str
    metadata_mapping_version: str
    accepted_values: Mapping[str, Any]
    exclusion_values: Mapping[str, Any] | None = None
    explicit_model_inclusions: tuple[str, ...] | list[str] = ()
    explicit_model_exclusions: tuple[str, ...] | list[str] = ()
    minimum_context_model_count: int = 1
    minimum_reference_model_count: int = 1
    limitations: tuple[str, ...] | list[str] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "accepted_values", _freeze(_sorted_values(self.accepted_values)))
        object.__setattr__(self, "exclusion_values", _freeze(_sorted_values(self.exclusion_values)))
        inclusions = tuple(sorted(set(self.explicit_model_inclusions)))
        exclusions = tuple(sorted(set(self.explicit_model_exclusions)))
        object.__setattr__(self, "explicit_model_inclusions", inclusions)
        object.__setattr__(self, "explicit_model_exclusions", exclusions)
        object.__setattr__(self, "limitations", tuple(sorted(set(self.limitations))))
        _require(self.context_definition_format_version == CONTEXT_FORMAT_VERSION, "unsupported context-definition format version")
        _require(all(_text(getattr(self, field)) for field in ("context_name", "context_version", "metadata_mapping_version")), "context identity fields must be non-empty")
        _require(set(inclusions).isdisjoint(exclusions), "explicit inclusion and exclusion conflict")
        _require(all(_text(value) for value in inclusions + exclusions + self.limitations), "context entries must be non-empty")
        _require(self.minimum_context_model_count >= 1 and self.minimum_reference_model_count >= 1, "context minimum counts must be positive")
        _safe(self.identity_payload())

    def identity_payload(self) -> dict[str, Any]:
        return {"context_definition_format_version": self.context_definition_format_version, "context_name": self.context_name,
                "context_version": self.context_version, "metadata_mapping_version": self.metadata_mapping_version,
                "accepted_values": _thaw(self.accepted_values), "exclusion_values": _thaw(self.exclusion_values),
                "explicit_model_inclusions": list(self.explicit_model_inclusions), "explicit_model_exclusions": list(self.explicit_model_exclusions),
                "minimum_context_model_count": self.minimum_context_model_count, "minimum_reference_model_count": self.minimum_reference_model_count,
                "limitations": list(self.limitations)}

    @property
    def context_definition_id(self) -> str:
        return _identity("dmcd", self.identity_payload())

    def to_dict(self) -> dict[str, Any]:
        return {**self.identity_payload(), "context_definition_id": self.context_definition_id}

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "DepMapModelContextDefinition":
        allowed = set(cls.__dataclass_fields__) | {"context_definition_id"}
        _require(set(data).issubset(allowed), "unknown context-definition fields")
        required = {"context_definition_format_version", "context_name", "context_version", "metadata_mapping_version", "accepted_values"}
        _require(required.issubset(data), "missing context-definition fields")
        item = cls(**{key: data[key] for key in cls.__dataclass_fields__ if key in data})
        _require(data.get("context_definition_id") in (None, item.context_definition_id), "context-definition ID does not match content")
        return item


@dataclass(frozen=True)
class FunctionalDependencyProfilePolicy:
    profile_policy_format_version: str
    minimum_measured_context_models: int
    minimum_measured_reference_models: int
    minimum_models_per_lineage: int
    minimum_eligible_lineages: int
    dependency_probability_thresholds: tuple[float, ...] | list[float]
    quantile_method: str
    missing_value_policy: str
    lineage_ranking_method: str
    contradiction_observation_rules: Mapping[str, Any]
    limitations: tuple[str, ...] | list[str] = ()

    def __post_init__(self) -> None:
        thresholds = tuple(sorted(set(float(value) for value in self.dependency_probability_thresholds)))
        object.__setattr__(self, "dependency_probability_thresholds", thresholds)
        object.__setattr__(self, "contradiction_observation_rules", _freeze(dict(sorted(self.contradiction_observation_rules.items()))))
        object.__setattr__(self, "limitations", tuple(sorted(set(self.limitations))))
        _require(self.profile_policy_format_version == POLICY_FORMAT_VERSION, "unsupported profile-policy format version")
        _require(all(value >= 1 for value in (self.minimum_measured_context_models, self.minimum_measured_reference_models, self.minimum_models_per_lineage, self.minimum_eligible_lineages)), "policy minimums must be positive")
        _require(thresholds and all(0 <= value <= 1 for value in thresholds), "probability thresholds must be between zero and one")
        _require(self.quantile_method == "linear", "only the documented linear quantile method is supported")
        _require(self.missing_value_policy == "exclude_and_report", "missing-value policy must exclude and report missing values")
        _require(self.lineage_ranking_method == "gene_effect_median_strength_percentile", "unknown lineage-ranking method")
        allowed_rules = {"strong_negative_gene_effect_at_or_below", "low_probability_at_or_below", "high_probability_at_or_above"}
        _require(set(self.contradiction_observation_rules).issubset(allowed_rules), "target-specific or unknown contradiction rules are not allowed")
        _require(all(isinstance(value, (int, float)) and math.isfinite(float(value)) for value in self.contradiction_observation_rules.values()), "contradiction rules must be finite numeric conventions")
        _require(all(_text(getattr(self, field)) for field in ("quantile_method", "missing_value_policy", "lineage_ranking_method")), "policy methods must be non-empty")
        _require(all(_text(value) for value in self.limitations), "policy limitations must be non-empty")
        _safe(self.identity_payload())

    def identity_payload(self) -> dict[str, Any]:
        return {"profile_policy_format_version": self.profile_policy_format_version, "minimum_measured_context_models": self.minimum_measured_context_models,
                "minimum_measured_reference_models": self.minimum_measured_reference_models, "minimum_models_per_lineage": self.minimum_models_per_lineage,
                "minimum_eligible_lineages": self.minimum_eligible_lineages, "dependency_probability_thresholds": list(self.dependency_probability_thresholds),
                "quantile_method": self.quantile_method, "missing_value_policy": self.missing_value_policy,
                "lineage_ranking_method": self.lineage_ranking_method, "contradiction_observation_rules": _thaw(self.contradiction_observation_rules), "limitations": list(self.limitations)}

    @property
    def profile_policy_id(self) -> str:
        return _identity("dmpp", self.identity_payload())

    def to_dict(self) -> dict[str, Any]: return {**self.identity_payload(), "profile_policy_id": self.profile_policy_id}

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "FunctionalDependencyProfilePolicy":
        allowed = set(cls.__dataclass_fields__) | {"profile_policy_id"}
        _require(set(data).issubset(allowed), "unknown profile-policy fields")
        required = set(cls.__dataclass_fields__) - {"limitations"}
        _require(required.issubset(data), "missing profile-policy fields")
        item = cls(**{key: data[key] for key in cls.__dataclass_fields__ if key in data})
        _require(data.get("profile_policy_id") in (None, item.profile_policy_id), "profile-policy ID does not match content")
        return item


def _number(value: str) -> float | None:
    if value == "": return None
    try: result = float(value)
    except ValueError as error: raise DepMapProfileError("normalized matrix contains invalid numeric value") from error
    if not math.isfinite(result): raise DepMapProfileError("normalized matrix contains non-finite numeric value")
    return result


def _read_tsv(path: Path) -> list[dict[str, str]]:
    _require(path.is_file(), f"required ingestion artifact is absent: {path.name}")
    try:
        with path.open("r", encoding="utf-8", newline="") as handle:
            return list(csv.DictReader(handle, delimiter="\t"))
    except (OSError, UnicodeError, csv.Error) as error:
        raise DepMapProfileError("ingestion artifact could not be read") from error


def _artifact_sha256(path: Path) -> str:
    """Return the deterministic identity of one declared derived artifact."""
    _require(path.is_file(), f"required ingestion artifact is absent: {path.name}")
    try:
        return sha256(path.read_bytes()).hexdigest()
    except OSError as error:
        raise DepMapProfileError("ingestion artifact could not be read") from error


def _index_identity(rows: list[dict[str, str]], kind: str, parser_version: str | None = None) -> str:
    """Reconstruct the canonical Issue 502 index identity from its TSV rows."""
    if kind == "gene":
        _require(parser_version is not None, "gene index parser version is absent from ingestion snapshot")
        normalized = [{**row, "source_column_index": int(row["source_column_index"]), "parser_version": parser_version,
                       **{field: (row[field] or None) for field in ("parsed_symbol", "parsed_entrez_identifier", "canonical_identity")}} for row in rows]
        return _identity("dmgi", {"rows": normalized})
    if kind == "model":
        normalized = [{**row,
                       "presence_in_gene_effect": row["presence_in_gene_effect"] == "True",
                       "presence_in_dependency_probability": row["presence_in_dependency_probability"] == "True",
                       "presence_in_metadata": row["presence_in_metadata"] == "True"} for row in rows]
        return _identity("dmmi", {"rows": normalized})
    if kind == "reference":
        normalized = [{**row, "source_row": int(row["source_row"]),
                       **{field: (row[field] or None) for field in ("parsed_symbol", "parsed_entrez_identifier", "canonical_identity")}} for row in rows]
        return _identity("dmri", {"rows": normalized})
    raise DepMapProfileError("unknown canonical index identity")


def _verify_snapshot_identity(snapshot: Mapping[str, Any]) -> None:
    payload = {key: value for key, value in snapshot.items() if key not in {"snapshot_id", "output_artifacts"}}
    _require(snapshot.get("snapshot_id") == _identity("dmis", payload), "ingestion snapshot identity does not match content")


def _summary(values: list[float | None], total: int, thresholds: tuple[float, ...]) -> dict[str, Any]:
    measured = sorted(value for value in values if value is not None)
    base = {"total_model_count": total, "measured_model_count": len(measured), "missing_model_count": total - len(measured),
            "missing_fraction": (total - len(measured)) / total if total else None}
    if not measured:
        return {**base, "available": False, "mean": None, "median": None, "minimum": None, "maximum": None, "first_quartile": None, "third_quartile": None, "interquartile_range": None,
                "threshold_fractions": [{"threshold": threshold, "numerator": 0, "denominator": 0, "fraction": None} for threshold in thresholds]}
    def quantile(position: float) -> float:
        index = (len(measured) - 1) * position; lower = math.floor(index); upper = math.ceil(index)
        return measured[lower] + (measured[upper] - measured[lower]) * (index - lower)
    q1, median, q3 = quantile(.25), quantile(.5), quantile(.75)
    return {**base, "available": True, "mean": sum(measured) / len(measured), "median": median, "minimum": measured[0], "maximum": measured[-1], "first_quartile": q1, "third_quartile": q3, "interquartile_range": q3 - q1,
            "threshold_fractions": [{"threshold": threshold, "numerator": sum(value >= threshold for value in measured), "denominator": len(measured), "fraction": sum(value >= threshold for value in measured) / len(measured)} for threshold in thresholds]}


def _context_index(model_rows: list[dict[str, str]], definition: DepMapModelContextDefinition) -> list[dict[str, Any]]:
    rows = []
    for row in sorted(model_rows, key=lambda value: value["model_identifier"]):
        model = row["model_identifier"]
        metadata = json.loads(row["structured_metadata"]) if row.get("structured_metadata") else None
        status, field, value, reason = "out_of_context", None, None, "no exact inclusion rule matched"
        if model in definition.explicit_model_exclusions:
            status, reason = "explicitly_excluded", "explicit model exclusion overrides context rules"
        elif model in definition.explicit_model_inclusions:
            status, reason = "explicitly_included", "explicit model inclusion"
        elif (
            row.get("presence_in_metadata") == "True"
            and row.get("presence_in_gene_effect") != "True"
            and row.get("presence_in_dependency_probability") != "True"
        ):
            # The canonical Issue 502 index deliberately retains metadata-only
            # models.  They cannot be classified as screened context models:
            # preserve that reconciliation state separately from a model whose
            # metadata itself is unavailable.
            status, reason = "model_not_reconciled", "model is present in metadata but absent from both dependency matrices"
        elif metadata is None:
            status, reason = "metadata_unavailable", "structured metadata unavailable in canonical model index"
        else:
            missing = [key for key in definition.accepted_values if not metadata.get(key)]
            exclude = [(key, metadata.get(key)) for key, values in definition.exclusion_values.items() if metadata.get(key) in values]
            matches = [(key, metadata.get(key)) for key, values in definition.accepted_values.items() if metadata.get(key) in values]
            if exclude and matches:
                status, field, value, reason = "ambiguous_context", exclude[0][0], exclude[0][1], "exact inclusion and exclusion rules both match"
            elif exclude:
                status, field, value, reason = "out_of_context", exclude[0][0], exclude[0][1], "exact exclusion value matched"
            elif missing:
                status, field, reason = "missing_required_metadata", missing[0], "required structured metadata field is missing"
            elif len(matches) == len(definition.accepted_values):
                status, field, value, reason = "in_context", matches[0][0], matches[0][1], "all exact structured inclusion values matched"
        rows.append({"model_identifier": model, "assignment_status": status, "matched_field": field, "matched_value": value, "assignment_reason": reason,
                     "source_metadata_provenance": row.get("source_provenance", ""), "context_definition_id": definition.context_definition_id})
    return rows


def _matrix(path: Path) -> tuple[list[str], dict[str, dict[str, float | None]]]:
    rows = _read_tsv(path); _require(rows and "ModelID" in rows[0], "normalized matrix has no ModelID")
    fields = [field for field in rows[0] if field != "ModelID"]; values = {}
    for row in rows:
        model = row["ModelID"]; _require(model and model not in values, "normalized matrix has invalid ModelID")
        values[model] = {field: _number(row.get(field, "")) for field in fields}
    return fields, values


def _reference_status(
    rows: list[dict[str, str]], role: str, canonical_identity: str | None,
    target_resolved: bool, release_manifest_id: str, validation_status: str | None,
) -> dict[str, Any]:
    """Report validated reference membership without treating absence as safety."""
    base = {"source_role": role, "release_identity": release_manifest_id}
    if validation_status is None:
        return {**base, "status": "reference_unavailable"}
    if validation_status != "valid":
        return {**base, "status": "reference_validation_failed"}
    if canonical_identity is None or not target_resolved:
        return {**base, "status": "target_unresolved_in_reference"}
    role_rows = [row for row in rows if row.get("dataset_role") == role]
    matches = sorted(row["original_source_label"] for row in role_rows if row.get("canonical_identity") == canonical_identity)
    return {**base, "status": "explicitly_present" if matches else "explicitly_absent",
            "matching_source_labels": matches}


@dataclass(frozen=True)
class FunctionalDependencyProfile:
    profile_format_version: str
    target_identity: Mapping[str, Any]
    release_manifest_id: str
    ingestion_snapshot_id: str
    target_universe_id: str | None
    context_definition_id: str
    profile_policy_id: str
    payload: Mapping[str, Any]
    terminal_status: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "target_identity", _freeze(self.target_identity)); object.__setattr__(self, "payload", _freeze(self.payload))
    def identity_payload(self) -> dict[str, Any]: return {"profile_format_version": self.profile_format_version, "target_identity": _thaw(self.target_identity), "release_manifest_id": self.release_manifest_id, "ingestion_snapshot_id": self.ingestion_snapshot_id, "target_universe_id": self.target_universe_id, "context_definition_id": self.context_definition_id, "profile_policy_id": self.profile_policy_id, "payload": _thaw(self.payload), "terminal_status": self.terminal_status}
    @property
    def profile_id(self) -> str: return _identity("dmfp", self.identity_payload())
    def to_dict(self) -> dict[str, Any]: return {**self.identity_payload(), "profile_id": self.profile_id}


@dataclass(frozen=True)
class FunctionalDependencyProfileRun:
    run_format_version: str
    ingestion_snapshot_id: str
    context_definition_id: str
    profile_policy_id: str
    target_universe_id: str | None
    profiles: tuple[FunctionalDependencyProfile, ...]
    limitations: tuple[str, ...]
    terminal_status: str = "valid"
    def identity_payload(self) -> dict[str, Any]: return {"run_format_version": self.run_format_version, "ingestion_snapshot_id": self.ingestion_snapshot_id, "context_definition_id": self.context_definition_id, "profile_policy_id": self.profile_policy_id, "target_universe_id": self.target_universe_id, "profile_ids": [item.profile_id for item in self.profiles], "limitations": list(self.limitations), "terminal_status": self.terminal_status}
    @property
    def run_id(self) -> str: return _identity("dmpr", self.identity_payload())


def build_dependency_profiles(ingestion_dir: Path | str, context: DepMapModelContextDefinition, policy: FunctionalDependencyProfilePolicy) -> tuple[FunctionalDependencyProfileRun, list[dict[str, Any]]]:
    root = Path(ingestion_dir); _require(root.is_absolute(), "ingestion directory must be explicit and absolute")
    try: snapshot = json.loads((root / "ingestion_snapshot.json").read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error: raise DepMapProfileError("ingestion snapshot could not be read") from error
    _require(snapshot.get("terminal_status") == "valid", "ingestion snapshot is not terminally valid")
    _verify_snapshot_identity(snapshot)
    _require(snapshot.get("mapping_version") == context.metadata_mapping_version, "context metadata mapping version is incompatible with ingestion snapshot")
    model_rows, gene_rows = _read_tsv(root / "model_index.tsv"), _read_tsv(root / "gene_index.tsv")
    _require(model_rows and "structured_metadata" in model_rows[0], "canonical model index does not expose structured metadata")
    _require(snapshot.get("model_index_id") == _index_identity(model_rows, "model"), "model index identity does not match ingestion snapshot")
    _require(snapshot.get("gene_index_id") == _index_identity(gene_rows, "gene", snapshot.get("parser_version")), "gene index identity does not match ingestion snapshot")
    reference_validation = {
        role: snapshot.get("dataset_validation_results", {}).get(role)
        for role in ("common_essential_reference", "pan_dependency_reference")
    }
    reference_rows: list[dict[str, str]] = []
    if any(status == "valid" for status in reference_validation.values()):
        _require("reference_index.tsv" in snapshot.get("output_artifacts", ()), "reference artifact is absent from ingestion snapshot")
        reference_rows = _read_tsv(root / "reference_index.tsv")
        _require(snapshot.get("reference_index_id") is not None, "reference identity is absent from ingestion snapshot")
        _require(snapshot.get("reference_index_id") == _index_identity(reference_rows, "reference"), "reference index identity does not match ingestion snapshot")
    canonical_by_label = {
        row["original_source_label"]: row.get("canonical_identity") or None
        for row in gene_rows if row.get("parser_status") == "parsed"
    }
    assignments = _context_index(model_rows, context)
    assignment_by_model = {item["model_identifier"]: item for item in assignments}
    matrix_artifact_ids = snapshot.get("subset_matrix_artifact_ids")
    _require(isinstance(matrix_artifact_ids, Mapping), "subset matrix identities are absent from ingestion snapshot")
    for role, filename in (("crispr_gene_effect", "gene_effect_subset.tsv"), ("crispr_dependency_probability", "dependency_probability_subset.tsv")):
        _require(matrix_artifact_ids.get(role) == _artifact_sha256(root / filename), "subset matrix identity does not match ingestion snapshot")
    effect_fields, effects = _matrix(root / "gene_effect_subset.tsv")
    probability_fields, probabilities = _matrix(root / "dependency_probability_subset.tsv")
    resolutions = sorted(snapshot.get("target_resolution_coverage", []), key=lambda item: canonical_json(item))
    profiles = []
    for resolution in resolutions:
        target = {key: resolution.get(key) for key in ("requested_identifier", "requested_identifier_type", "normalized_request", "matched_original_source_label", "resolution_status")}
        label = resolution.get("matched_original_source_label")
        status = resolution.get("resolution_status", "unresolved")
        effect_present, probability_present = bool(label and label in effect_fields), bool(label and label in probability_fields)
        matrix_coverage = "target_unresolved" if not status.startswith("resolved_") else ("target_resolved_both_matrices" if effect_present and probability_present else "target_present_only_gene_effect" if effect_present else "target_present_only_dependency_probability" if probability_present else "target_unresolved")
        coverage = matrix_coverage
        group_models = {"context": sorted(model for model, item in assignment_by_model.items() if item["assignment_status"] in {"in_context", "explicitly_included"}),
                        "non_context": sorted(model for model, item in assignment_by_model.items() if item["assignment_status"] not in {"in_context", "explicitly_included"}),
                        "pan_cancer": sorted(assignment_by_model)}
        summaries = {}
        for group, models in group_models.items():
            summaries[group] = {"gene_effect": _summary([effects.get(model, {}).get(label) if effect_present else None for model in models], len(models), ()),
                                "dependency_probability": _summary([probabilities.get(model, {}).get(label) if probability_present else None for model in models], len(models), policy.dependency_probability_thresholds)}
        context_effect, reference_effect = summaries["context"]["gene_effect"], summaries["non_context"]["gene_effect"]
        context_probability, reference_probability = summaries["context"]["dependency_probability"], summaries["non_context"]["dependency_probability"]
        if status.startswith("resolved_"):
            if not group_models["context"]: coverage = "no_context_models"
            elif effect_present and context_effect["measured_model_count"] == 0 and probability_present and context_probability["measured_model_count"] == 0: coverage = "context_models_all_values_missing"
            elif context_effect["measured_model_count"] < policy.minimum_measured_context_models and context_probability["measured_model_count"] < policy.minimum_measured_context_models: coverage = "insufficient_measured_context_models"
            elif reference_effect["measured_model_count"] < policy.minimum_measured_reference_models and reference_probability["measured_model_count"] < policy.minimum_measured_reference_models: coverage = "insufficient_measured_reference_models"
            elif effect_present and probability_present: coverage = "sufficient_complete_coverage"
            elif effect_present or probability_present: coverage = "sufficient_partial_coverage"
        contrasts = {
            "gene_effect_context_minus_non_context_median": None,
            "gene_effect_context_minus_non_context_mean": None,
            "dependency_probability_context_minus_non_context_median": None,
            "dependency_probability_context_minus_non_context_threshold_fractions": [],
            "context_minus_pan_cancer": {
                "gene_effect_median": None,
                "gene_effect_mean": None,
                "dependency_probability_median": None,
                "dependency_probability_threshold_fractions": [],
            },
            "direction": "Negative gene-effect context-minus-reference values indicate stronger model dependency signal in the context group.",
        }
        # A descriptive contrast is unavailable unless the relevant source has
        # met the explicit policy coverage requirement in both groups.  The
        # raw summaries remain present so missingness and partial observation
        # are still reviewable without presenting an under-covered difference.
        effect_contrast_covered = (
            context_effect["measured_model_count"] >= policy.minimum_measured_context_models
            and reference_effect["measured_model_count"] >= policy.minimum_measured_reference_models
        )
        probability_contrast_covered = (
            context_probability["measured_model_count"] >= policy.minimum_measured_context_models
            and reference_probability["measured_model_count"] >= policy.minimum_measured_reference_models
        )
        if effect_contrast_covered:
            contrasts["gene_effect_context_minus_non_context_median"] = context_effect["median"] - reference_effect["median"]; contrasts["gene_effect_context_minus_non_context_mean"] = context_effect["mean"] - reference_effect["mean"]
        if probability_contrast_covered:
            contrasts["dependency_probability_context_minus_non_context_median"] = context_probability["median"] - reference_probability["median"]
            contrasts["dependency_probability_context_minus_non_context_threshold_fractions"] = [
                {
                    "threshold": context_fraction["threshold"],
                    "context_fraction": context_fraction["fraction"],
                    "non_context_fraction": reference_fraction["fraction"],
                    "difference": context_fraction["fraction"] - reference_fraction["fraction"],
                }
                for context_fraction, reference_fraction in zip(
                    context_probability["threshold_fractions"],
                    reference_probability["threshold_fractions"],
                    strict=True,
                )
            ]
        pan_effect = summaries["pan_cancer"]["gene_effect"]
        pan_probability = summaries["pan_cancer"]["dependency_probability"]
        pan_effect_contrast_covered = (
            context_effect["measured_model_count"] >= policy.minimum_measured_context_models
            and pan_effect["measured_model_count"] >= policy.minimum_measured_reference_models
        )
        pan_probability_contrast_covered = (
            context_probability["measured_model_count"] >= policy.minimum_measured_context_models
            and pan_probability["measured_model_count"] >= policy.minimum_measured_reference_models
        )
        if pan_effect_contrast_covered:
            contrasts["context_minus_pan_cancer"]["gene_effect_median"] = context_effect["median"] - pan_effect["median"]
            contrasts["context_minus_pan_cancer"]["gene_effect_mean"] = context_effect["mean"] - pan_effect["mean"]
        if pan_probability_contrast_covered:
            contrasts["context_minus_pan_cancer"]["dependency_probability_median"] = context_probability["median"] - pan_probability["median"]
            contrasts["context_minus_pan_cancer"]["dependency_probability_threshold_fractions"] = [
                {
                    "threshold": context_fraction["threshold"],
                    "context_fraction": context_fraction["fraction"],
                    "pan_cancer_fraction": pan_fraction["fraction"],
                    "difference": context_fraction["fraction"] - pan_fraction["fraction"],
                }
                for context_fraction, pan_fraction in zip(
                    context_probability["threshold_fractions"],
                    pan_probability["threshold_fractions"],
                    strict=True,
                )
            ]
        lines = []
        for lineage in sorted({json.loads(row["structured_metadata"]).get("OncotreeLineage", "") if row.get("structured_metadata") else "" for row in model_rows}):
            models = sorted(row["model_identifier"] for row in model_rows if row.get("structured_metadata") and json.loads(row["structured_metadata"]).get("OncotreeLineage", "") == lineage)
            ge = _summary([effects.get(model, {}).get(label) if effect_present else None for model in models], len(models), ()); dp = _summary([probabilities.get(model, {}).get(label) if probability_present else None for model in models], len(models), policy.dependency_probability_thresholds)
            lines.append({"lineage_identifier": lineage or "metadata_missing", "eligible": len(models) >= policy.minimum_models_per_lineage, "gene_effect": ge, "dependency_probability": dp})
        eligible = [line for line in lines if line["eligible"] and line["gene_effect"]["available"]]
        position = {"available": False, "eligible_lineage_count": len(eligible), "value": None, "direction": "100 means a stronger (more negative median gene-effect) context signal than most eligible lineages."}
        context_lineages = {json.loads(row["structured_metadata"]).get("OncotreeLineage", "") for row in model_rows if row["model_identifier"] in group_models["context"] and row.get("structured_metadata")}
        if len(eligible) >= policy.minimum_eligible_lineages and len(context_lineages) == 1:
            context_line = next(iter(context_lineages)); item = next((line for line in eligible if line["lineage_identifier"] == context_line), None)
            if item:
                stronger = sum(line["gene_effect"]["median"] > item["gene_effect"]["median"] for line in eligible); equal = sum(line["gene_effect"]["median"] == item["gene_effect"]["median"] for line in eligible)
                position.update({"available": True, "value": 100 * (stronger + (equal - 1) / 2) / max(1, len(eligible) - 1)})
        observations = []
        if context_effect["available"]:
            vals = [(model, effects.get(model, {}).get(label)) for model in group_models["context"] if effects.get(model, {}).get(label) is not None]
            observations = [{"model_identifier": model, "gene_effect": value, "dependency_probability": probabilities.get(model, {}).get(label) if probability_present else None} for model, value in sorted(vals, key=lambda item: (item[1], item[0]))]
        contradictions = []
        rules = _thaw(policy.contradiction_observation_rules); strong = rules.get("strong_negative_gene_effect_at_or_below"); low = rules.get("low_probability_at_or_below"); high = rules.get("high_probability_at_or_above")
        if strong is not None and low is not None:
            for item in observations:
                if item["gene_effect"] <= strong and item["dependency_probability"] is not None and item["dependency_probability"] <= low: contradictions.append({"type": "strong_negative_gene_effect_low_probability", **item})
        if high is not None:
            for item in observations:
                if item["gene_effect"] is not None and strong is not None and item["gene_effect"] > strong and item["dependency_probability"] is not None and item["dependency_probability"] >= high: contradictions.append({"type": "weak_gene_effect_high_probability", **item})
        common_reference = _reference_status(reference_rows, "common_essential_reference", canonical_by_label.get(label or ""), status.startswith("resolved_"), snapshot["release_manifest_id"], reference_validation["common_essential_reference"])
        pan_reference = _reference_status(reference_rows, "pan_dependency_reference", canonical_by_label.get(label or ""), status.startswith("resolved_"), snapshot["release_manifest_id"], reference_validation["pan_dependency_reference"])
        source_availability = {"gene_effect_available": context_effect["available"], "dependency_probability_available": context_probability["available"]}
        if source_availability["gene_effect_available"] != source_availability["dependency_probability_available"]:
            contradictions.append({"type": "context_signal_present_only_one_matrix", **source_availability,
                                   "gene_effect_measured_model_count": context_effect["measured_model_count"],
                                   "dependency_probability_measured_model_count": context_probability["measured_model_count"]})
        if not all(source_availability.values()):
            contradictions.append({"type": "insufficient_data_for_concordance_assessment", **source_availability,
                                   "gene_effect_measured_model_count": context_effect["measured_model_count"],
                                   "dependency_probability_measured_model_count": context_probability["measured_model_count"]})
        for source, context_summary, reference_summary, pan_summary in (
            ("gene_effect", context_effect, reference_effect, summaries["pan_cancer"]["gene_effect"]),
            ("dependency_probability", context_probability, reference_probability, summaries["pan_cancer"]["dependency_probability"]),
        ):
            if context_summary["available"] and reference_summary["available"] and pan_summary["available"]:
                context_minus_reference = context_summary["median"] - reference_summary["median"]
                context_minus_pan_cancer = context_summary["median"] - pan_summary["median"]
                if context_minus_reference * context_minus_pan_cancer < 0:
                    contradictions.append({"type": "context_and_pan_cancer_summaries_point_in_different_directions", "source": source,
                                           "context_median": context_summary["median"], "non_context_median": reference_summary["median"],
                                           "pan_cancer_median": pan_summary["median"], "context_minus_non_context_median": context_minus_reference,
                                           "context_minus_pan_cancer_median": context_minus_pan_cancer})
        if contrasts["gene_effect_context_minus_non_context_median"] is not None and contrasts["gene_effect_context_minus_non_context_median"] < 0:
            for reference_name, reference in (("common_essential_reference", common_reference), ("pan_dependency_reference", pan_reference)):
                if reference["status"] == "explicitly_present":
                    contradictions.append({"type": "optional_reference_membership_conflicts_with_descriptive_context_selectivity",
                                           "reference_name": reference_name, "reference_status": reference["status"],
                                           "context_minus_non_context_gene_effect_median": contrasts["gene_effect_context_minus_non_context_median"]})
        payload = {"target_resolution_status": status, "matrix_coverage_status": matrix_coverage, "coverage_status": coverage, "model_coverage": {"context_model_count": len(group_models["context"]), "non_context_model_count": len(group_models["non_context"]), "pan_cancer_model_count": len(group_models["pan_cancer"])}, "summaries": summaries, "contrasts": contrasts, "lineage_summaries": lines, "empirical_context_lineage_position": position, "heterogeneity_observations": observations, "contradiction_observations": contradictions,
                   "common_essential_reference": common_reference, "pan_dependency_reference": pan_reference,
                   "limitations": ["Descriptive synthetic-fixture evidence only; no therapeutic, clinical, safety, or causal conclusion."] + list(context.limitations) + list(policy.limitations)}
        profiles.append(FunctionalDependencyProfile(PROFILE_FORMAT_VERSION, target, snapshot["release_manifest_id"], snapshot["snapshot_id"], snapshot.get("target_universe_id"), context.context_definition_id, policy.profile_policy_id, payload, "valid" if status.startswith("resolved_") else "unavailable"))
    profiles.sort(key=lambda item: canonical_json(_thaw(item.target_identity)))
    run = FunctionalDependencyProfileRun(RUN_FORMAT_VERSION, snapshot["snapshot_id"], context.context_definition_id, policy.profile_policy_id, snapshot.get("target_universe_id"), tuple(profiles), ("Profiles consume canonical Issue 502 derived artifacts only.",))
    return run, assignments


def write_dependency_profile_artifacts(output_dir: Path | str, run: FunctionalDependencyProfileRun, assignments: list[dict[str, Any]]) -> None:
    output = Path(output_dir); _require(output.is_absolute(), "output directory must be explicit and absolute"); output.mkdir(parents=True, exist_ok=True)
    def write(name: str, text: str) -> None:
        temporary = output / f".{name}.tmp"; temporary.write_text(text, encoding="utf-8", newline=""); temporary.replace(output / name)
    manifest = {**run.identity_payload(), "run_id": run.run_id, "requested_target_count": len(run.profiles), "profile_count": len(run.profiles), "terminal_status_counts": {status: sum(item.terminal_status == status for item in run.profiles) for status in sorted({item.terminal_status for item in run.profiles})}, "output_artifacts": ["dependency_coverage_summary.json", "dependency_profile_manifest.json", "dependency_profile_summary.tsv", "dependency_profiles.jsonl", "model_context_index.tsv"]}
    write("dependency_profiles.jsonl", "".join(canonical_json(item.to_dict()) + "\n" for item in run.profiles))
    fields = ["target", "resolution_status", "coverage_status", "context_total_models", "context_measured_gene_effect_models", "context_median_gene_effect", "non_context_median_gene_effect", "gene_effect_median_difference", "context_measured_probability_models", "context_median_dependency_probability", "context_fraction_above_first_threshold", "non_context_fraction_above_first_threshold", "empirical_context_lineage_position", "common_essential_reference_status", "pan_dependency_reference_status", "contradiction_count", "limitation_count", "profile_status"]
    rows = []
    for item in run.profiles:
        data = _thaw(item.payload); summaries = data["summaries"]; cp, np = summaries["context"]["dependency_probability"], summaries["non_context"]["dependency_probability"]
        rows.append({"target": item.target_identity["normalized_request"], "resolution_status": data["target_resolution_status"], "coverage_status": data["coverage_status"], "context_total_models": data["model_coverage"]["context_model_count"], "context_measured_gene_effect_models": summaries["context"]["gene_effect"]["measured_model_count"], "context_median_gene_effect": summaries["context"]["gene_effect"]["median"], "non_context_median_gene_effect": summaries["non_context"]["gene_effect"]["median"], "gene_effect_median_difference": data["contrasts"]["gene_effect_context_minus_non_context_median"], "context_measured_probability_models": cp["measured_model_count"], "context_median_dependency_probability": cp["median"], "context_fraction_above_first_threshold": cp["threshold_fractions"][0]["fraction"], "non_context_fraction_above_first_threshold": np["threshold_fractions"][0]["fraction"], "empirical_context_lineage_position": data["empirical_context_lineage_position"]["value"], "common_essential_reference_status": data["common_essential_reference"]["status"], "pan_dependency_reference_status": data["pan_dependency_reference"]["status"], "contradiction_count": len(data["contradiction_observations"]), "limitation_count": len(data["limitations"]), "profile_status": item.terminal_status})
    write("dependency_profile_summary.tsv", "\t".join(fields) + "\n" + "".join("\t".join("" if row[field] is None else str(row[field]) for field in fields) + "\n" for row in rows))
    write("dependency_coverage_summary.json", canonical_json({"run_id": run.run_id, "coverage_counts": {state: sum(_thaw(item.payload)["coverage_status"] == state for item in run.profiles) for state in sorted({_thaw(item.payload)["coverage_status"] for item in run.profiles})}}) + "\n")
    assignment_fields = ["model_identifier", "assignment_status", "matched_field", "matched_value", "assignment_reason", "source_metadata_provenance", "context_definition_id"]
    write("model_context_index.tsv", "\t".join(assignment_fields) + "\n" + "".join("\t".join("" if row[field] is None else str(row[field]) for field in assignment_fields) + "\n" for row in assignments))
    # The terminal success artifact is deliberately last: a write failure for a
    # dependent artifact must not leave a success manifest behind.
    write("dependency_profile_manifest.json", canonical_json(manifest) + "\n")

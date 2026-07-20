"""Offline, immutable target-universe contracts for the v0.5.0 study.

This module deliberately has no dependency-profile, scoring, ranking, or remote
execution surface. It only freezes supplied, pre-DepMap curation records.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping, Sequence
import yaml

from .depmap_models import canonical_json

FORMAT_VERSION = "v0.5.0"
UNIVERSE_TYPES = frozenset({"benchmark", "discovery", "background"})
BENCHMARK_CLASSES = frozenset({"known_positive", "negative_control", "challenging_control", "context_dependent", "biomarker_not_intervention_target", "mechanism_control", "unknown_or_holdout"})
PARTITIONS = frozenset({"development", "holdout"})

def _canonical_resistance_axes() -> frozenset[str]:
    """Read the repository's canonical axis keys without creating aliases."""
    config_path = Path(__file__).resolve().parents[2] / "configs" / "resistance_axes.yaml"
    loaded = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    if not isinstance(loaded, Mapping) or not all(isinstance(key, str) for key in loaded):
        raise ValueError("canonical resistance-axis configuration is invalid")
    return frozenset(loaded) | {"other_unresolved"}


# The explicit unresolved state is not an ontology axis; every other accepted
# key is read directly from configs/resistance_axes.yaml.
RESISTANCE_AXES = _canonical_resistance_axes()
APPROVED_SOURCE_CLASSES = frozenset({"opentargets_candidate", "resistance_axis", "curated_mechanism", "published_crispr_candidate", "druggable_list", "receptor_ligand", "existing_evidence_candidate", "benchmark_union"})
FORBIDDEN_MARKERS = frozenset({"depmap", "gene_effect", "dependency_probability", "lineage_position", "lineage_selectivity", "common_essential", "pan_dependency", "profile_status", "benchmark_result", "expected_behaviour", "expected_behavior", "current_rank", "targetintel_rank", "score", "ranking", "holdout_label", "chain_of_thought", "reasoning", "credential", "password", "secret", "token", "authorization"})


def _id(prefix: str, value: Any) -> str:
    return f"{prefix}_{sha256(canonical_json(value).encode('utf-8')).hexdigest()}"


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _frozen_mapping(value: Mapping[str, Any] | None = None) -> Mapping[str, Any]:
    return MappingProxyType(dict(value or {}))


def _axes(values: Sequence[str] | str) -> tuple[str, ...]:
    items = [values] if isinstance(values, str) else values
    result = tuple(sorted({_text(item) for item in items if _text(item)}))
    if not result or not set(result).issubset(RESISTANCE_AXES):
        raise ValueError("invalid controlled resistance axis")
    return result


def _forbidden(value: Any, path: str = "") -> str | None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            key_text = str(key).casefold()
            if any(marker in key_text for marker in FORBIDDEN_MARKERS):
                return f"forbidden field: {path}{key}"
            found = _forbidden(item, f"{path}{key}.")
            if found:
                return found
    elif isinstance(value, (tuple, list)):
        for index, item in enumerate(value):
            found = _forbidden(item, f"{path}{index}.")
            if found:
                return found
    return None


@dataclass(frozen=True)
class InclusionSourceRecord:
    source_class: str
    source_record_id: str
    dataset_version: str
    inclusion_rule: str
    limitations: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.source_class not in APPROVED_SOURCE_CLASSES or not all(_text(v) for v in (self.source_record_id, self.dataset_version, self.inclusion_rule)):
            raise ValueError("invalid or unapproved inclusion source")
        object.__setattr__(self, "limitations", tuple(sorted(set(self.limitations))))

    @property
    def source_id(self) -> str:
        return _id("tus", self.to_dict())

    def to_dict(self) -> dict[str, Any]:
        return {"source_class": self.source_class, "source_record_id": self.source_record_id, "dataset_version": self.dataset_version, "inclusion_rule": self.inclusion_rule, "limitations": list(self.limitations)}


@dataclass(frozen=True)
class TargetUniverseEntry:
    entry_format_version: str
    original_identifier: str
    canonical_identity: str
    universe_type: str
    inclusion_sources: tuple[InclusionSourceRecord, ...]
    resistance_axes: tuple[str, ...]
    role_annotation: str | None = None
    resolution_status: str = "resolved_exact"
    inclusion_status: str = "included"
    rejection_reason: str | None = None
    limitations: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "inclusion_sources", tuple(sorted(set(self.inclusion_sources), key=lambda item: item.source_id)))
        object.__setattr__(self, "resistance_axes", _axes(self.resistance_axes))
        object.__setattr__(self, "limitations", tuple(sorted(set(self.limitations))))
        if self.entry_format_version != FORMAT_VERSION or self.universe_type not in UNIVERSE_TYPES or not _text(self.original_identifier) or not _text(self.canonical_identity):
            raise ValueError("invalid target-universe entry")
        if self.inclusion_status not in {"included", "unresolved", "rejected"}:
            raise ValueError("invalid inclusion status")
        if self.inclusion_status == "included" and not self.inclusion_sources:
            raise ValueError("included entry requires provenance")
        if self.inclusion_status != "included" and not _text(self.rejection_reason):
            raise ValueError("non-included entry requires a reason")

    @property
    def entry_id(self) -> str:
        return _id("tue", self.identity_payload())

    def identity_payload(self) -> dict[str, Any]:
        return {"entry_format_version": self.entry_format_version, "original_identifier": self.original_identifier, "canonical_identity": self.canonical_identity, "universe_type": self.universe_type, "inclusion_source_ids": [item.source_id for item in self.inclusion_sources], "resistance_axes": list(self.resistance_axes), "role_annotation": self.role_annotation, "resolution_status": self.resolution_status, "inclusion_status": self.inclusion_status, "rejection_reason": self.rejection_reason, "limitations": list(self.limitations)}

    def to_dict(self) -> dict[str, Any]:
        return {**self.identity_payload(), "entry_id": self.entry_id, "inclusion_sources": [item.to_dict() for item in self.inclusion_sources]}


@dataclass(frozen=True)
class BenchmarkEntry:
    entry: TargetUniverseEntry
    benchmark_class: str
    expected_qualitative_behaviour: str
    role: str
    evidence_source_key: str
    curation_rationale: str
    partition: str
    curation_version: str
    limitations: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "limitations", tuple(sorted(set(self.limitations))))
        if self.entry.universe_type != "benchmark" or self.benchmark_class not in BENCHMARK_CLASSES or self.partition not in PARTITIONS:
            raise ValueError("invalid benchmark class or partition")
        if not all(_text(v) for v in (self.expected_qualitative_behaviour, self.role, self.evidence_source_key, self.curation_rationale, self.curation_version)):
            raise ValueError("benchmark curation fields are required")
        forbidden = _forbidden({"expected_qualitative_behaviour": self.expected_qualitative_behaviour})
        if forbidden and self.benchmark_class != "unknown_or_holdout":
            raise ValueError(forbidden)

    def to_dict(self) -> dict[str, Any]:
        return {**self.entry.to_dict(), "benchmark_class": self.benchmark_class, "expected_qualitative_behaviour": self.expected_qualitative_behaviour, "role": self.role, "evidence_source_key": self.evidence_source_key, "curation_rationale": self.curation_rationale, "partition": self.partition, "curation_version": self.curation_version, "benchmark_limitations": list(self.limitations)}


@dataclass(frozen=True)
class DiscoveryUniversePolicy:
    policy_format_version: str
    policy_id_label: str
    approved_source_classes: tuple[str, ...]
    source_specific_inclusion_rules: Mapping[str, str]
    canonical_identity_mapping_version: str
    benchmark_union_required: bool
    exclusion_rules: tuple[str, ...]
    advisory_maximum_size: int | None
    limitations: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "approved_source_classes", tuple(sorted(set(self.approved_source_classes))))
        object.__setattr__(self, "source_specific_inclusion_rules", _frozen_mapping(self.source_specific_inclusion_rules))
        object.__setattr__(self, "exclusion_rules", tuple(sorted(set(self.exclusion_rules))))
        object.__setattr__(self, "limitations", tuple(sorted(set(self.limitations))))
        if self.policy_format_version != FORMAT_VERSION or not _text(self.policy_id_label) or not _text(self.canonical_identity_mapping_version): raise ValueError("invalid discovery policy")
        if not set(self.approved_source_classes).issubset(APPROVED_SOURCE_CLASSES) or not self.approved_source_classes: raise ValueError("unknown source class")
        if set(self.source_specific_inclusion_rules) != set(self.approved_source_classes): raise ValueError("policy requires explicit rule for every source class")
        if _forbidden(self.source_specific_inclusion_rules): raise ValueError("forbidden discovery-policy field")

    @property
    def policy_id(self) -> str: return _id("dup", self.to_dict())
    def to_dict(self) -> dict[str, Any]: return {"policy_format_version": self.policy_format_version, "policy_id_label": self.policy_id_label, "approved_source_classes": list(self.approved_source_classes), "source_specific_inclusion_rules": dict(self.source_specific_inclusion_rules), "canonical_identity_mapping_version": self.canonical_identity_mapping_version, "benchmark_union_required": self.benchmark_union_required, "exclusion_rules": list(self.exclusion_rules), "advisory_maximum_size": self.advisory_maximum_size, "limitations": list(self.limitations)}


@dataclass(frozen=True)
class TargetUniverse:
    universe_type: str
    universe_version: str
    entries: tuple[TargetUniverseEntry, ...]
    limitations: tuple[str, ...] = ()
    construction_policy_id: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "entries", tuple(sorted(self.entries, key=lambda item: item.canonical_identity)))
        object.__setattr__(self, "limitations", tuple(sorted(set(self.limitations))))
        identities = [item.canonical_identity for item in self.entries if item.inclusion_status == "included"]
        if self.universe_type not in UNIVERSE_TYPES or not _text(self.universe_version) or len(identities) != len(set(identities)):
            raise ValueError("invalid universe or duplicate canonical identity")
        if any(item.universe_type != self.universe_type for item in self.entries): raise ValueError("entry universe type mismatch")
    @property
    def universe_id(self) -> str: return _id("tu", self.identity_payload())
    def identity_payload(self) -> dict[str, Any]: return {"universe_type": self.universe_type, "universe_version": self.universe_version, "entries": [item.entry_id for item in self.entries], "limitations": list(self.limitations), "construction_policy_id": self.construction_policy_id}


@dataclass(frozen=True)
class TargetUniverseFreezeManifest:
    context_identity: str; disease_identity: str; benchmark_universe_id: str; discovery_universe_id: str; background_universe_id: str; construction_policy_ids: tuple[str, ...]; source_dataset_versions: tuple[str, ...]; canonical_mapping_version: str; overlap_report_id: str; unresolved_target_report_id: str; limitations: tuple[str, ...]; terminal_status: str = "frozen"
    def __post_init__(self) -> None:
        object.__setattr__(self, "construction_policy_ids", tuple(sorted(set(self.construction_policy_ids))))
        object.__setattr__(self, "source_dataset_versions", tuple(sorted(set(self.source_dataset_versions))))
        object.__setattr__(self, "limitations", tuple(sorted(set(self.limitations))))
        if self.terminal_status != "frozen" or not all(_text(v) for v in (self.context_identity, self.disease_identity, self.benchmark_universe_id, self.discovery_universe_id, self.background_universe_id, self.canonical_mapping_version, self.overlap_report_id, self.unresolved_target_report_id)): raise ValueError("invalid freeze manifest")
    @property
    def freeze_id(self) -> str: return _id("tufm", self.to_dict())
    def to_dict(self) -> dict[str, Any]: return {"freeze_manifest_format_version": FORMAT_VERSION, "context_identity": self.context_identity, "disease_identity": self.disease_identity, "benchmark_universe_id": self.benchmark_universe_id, "discovery_universe_id": self.discovery_universe_id, "background_universe_id": self.background_universe_id, "construction_policy_ids": list(self.construction_policy_ids), "source_dataset_versions": list(self.source_dataset_versions), "canonical_mapping_version": self.canonical_mapping_version, "overlap_report_id": self.overlap_report_id, "unresolved_target_report_id": self.unresolved_target_report_id, "limitations": list(self.limitations), "terminal_status": self.terminal_status}


def leakage_audit(value: Mapping[str, Any]) -> dict[str, Any]:
    finding = _forbidden(value)
    if finding: raise ValueError(finding)
    return {"audit_format_version": FORMAT_VERSION, "terminal_status": "passed", "forbidden_field_detection": "recursive", "contains_target_outcomes": False, "contains_scores": False, "contains_rankings": False}


def read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle: return list(csv.DictReader(handle, delimiter="\t"))


def _sources(row: Mapping[str, str]) -> tuple[InclusionSourceRecord, ...]:
    source_class = _text(row.get("source_class"))
    if not source_class: return ()
    return (InclusionSourceRecord(source_class, _text(row.get("source_record_id")), _text(row.get("source_dataset_version")), _text(row.get("inclusion_rule")), tuple(filter(None, _text(row.get("limitations")).split("|"))),),)


def _entry(row: Mapping[str, str], universe_type: str) -> TargetUniverseEntry:
    axes = tuple(filter(None, _text(row.get("resistance_axes") or row.get("resistance_axis") or "other_unresolved").split("|")))
    status = _text(row.get("inclusion_status")) or "included"
    return TargetUniverseEntry(FORMAT_VERSION, _text(row.get("original_gene_symbol") or row.get("gene_symbol")), _text(row.get("canonical_identity")), universe_type, _sources(row), axes, _text(row.get("role_annotation")) or None, _text(row.get("resolution_status")) or "resolved_exact", status, _text(row.get("rejection_reason")) or None, tuple(filter(None, _text(row.get("limitations")).split("|"))))


def load_benchmark(path: Path) -> tuple[TargetUniverse, tuple[BenchmarkEntry, ...]]:
    entries = []
    for row in read_tsv(path):
        entry = _entry({**row, "source_class": "benchmark_union", "source_record_id": row.get("evidence_source_key", ""), "source_dataset_version": row.get("curation_version", ""), "inclusion_rule": "curated benchmark entry"}, "benchmark")
        entries.append(BenchmarkEntry(entry, _text(row.get("benchmark_class")), _text(row.get("expected_qualitative_behaviour")), _text(row.get("role")), _text(row.get("evidence_source_key")), _text(row.get("curation_rationale")), _text(row.get("partition")), _text(row.get("curation_version")), tuple(filter(None, _text(row.get("entry_limitations")).split("|")))))
    if not entries: raise ValueError("benchmark is empty")
    if not any(item.partition == "holdout" for item in entries): raise ValueError("benchmark requires holdout partition")
    universe = TargetUniverse("benchmark", "benchmark_v1", tuple(item.entry for item in entries), ("Internal curated benchmark; not independent validation.",))
    return universe, tuple(entries)


def load_policy(path: Path) -> DiscoveryUniversePolicy:
    data = json.loads(path.read_text(encoding="utf-8"))
    return DiscoveryUniversePolicy(**data)


def load_discovery(path: Path, policy: DiscoveryUniversePolicy, benchmark: TargetUniverse) -> tuple[TargetUniverse, tuple[TargetUniverseEntry, ...]]:
    raw = read_tsv(path); leakage_audit({"records": raw})
    entries = [_entry(row, "discovery") for row in raw]
    for item in entries:
        if item.inclusion_status == "included" and not {source.source_class for source in item.inclusion_sources}.issubset(policy.approved_source_classes): raise ValueError("source class not approved by discovery policy")
    if policy.benchmark_union_required:
        existing = {item.canonical_identity for item in entries}
        entries.extend(TargetUniverseEntry(FORMAT_VERSION, item.original_identifier, item.canonical_identity, "discovery", (InclusionSourceRecord("benchmark_union", item.canonical_identity, benchmark.universe_version, "policy-required benchmark union"),), item.resistance_axes, item.role_annotation, limitations=item.limitations) for item in benchmark.entries if item.canonical_identity not in existing)
    included = tuple(item for item in entries if item.inclusion_status == "included")
    return TargetUniverse("discovery", "discovery_v1", included, ("Membership is pre-DepMap and does not imply suitability.",), policy.policy_id), tuple(item for item in entries if item.inclusion_status != "included")


def load_background(gene_index: Path, release_manifest_id: str, mapping_version: str) -> tuple[TargetUniverse, tuple[dict[str, str], ...]]:
    if not _text(release_manifest_id) or not _text(mapping_version): raise ValueError("background requires release and mapping identities")
    rows = read_tsv(gene_index); malformed = tuple(row for row in rows if row.get("parser_status") != "parsed")
    valid = [row for row in rows if row.get("parser_status") == "parsed" and _text(row.get("canonical_identity"))]
    grouped: dict[str, list[dict[str, str]]] = {}
    for row in valid: grouped.setdefault(row["canonical_identity"], []).append(row)
    ambiguous = {identity for identity, group in grouped.items() if len({row["original_source_label"] for row in group}) > 1}
    entries = tuple(TargetUniverseEntry(FORMAT_VERSION, group[0]["parsed_symbol"], identity, "background", tuple(InclusionSourceRecord("existing_evidence_candidate", f"gene-index:{row['dataset_role']}:{row['source_column_index']}", release_manifest_id, "valid full-matrix gene-index column") for row in group), ("other_unresolved",), resolution_status="valid_matrix_gene") for identity, group in grouped.items() if identity not in ambiguous)
    malformed = malformed + tuple(row for identity, group in grouped.items() if identity in ambiguous for row in group)
    return TargetUniverse("background", "background_v1", entries, (f"release_manifest_id={release_manifest_id}", f"mapping_version={mapping_version}", "Duplicate canonical identities are excluded rather than merged."), _id("bgi", {"release_manifest_id": release_manifest_id, "mapping_version": mapping_version, "gene_index": sorted((r.get('dataset_role'), r.get('source_column_index'), r.get('canonical_identity')) for r in rows)})), malformed


def overlap_report(benchmark: TargetUniverse, discovery: TargetUniverse, background: TargetUniverse, unresolved: Sequence[TargetUniverseEntry] = ()) -> dict[str, Any]:
    sets = {name: {item.canonical_identity for item in universe.entries} for name, universe in (("benchmark", benchmark), ("discovery", discovery), ("background", background))}
    report = {"benchmark_vs_discovery": sorted(sets["benchmark"] & sets["discovery"]), "benchmark_vs_background": sorted(sets["benchmark"] & sets["background"]), "discovery_vs_background": sorted(sets["discovery"] & sets["background"]), "benchmark_absent_from_discovery": sorted(sets["benchmark"] - sets["discovery"]), "benchmark_absent_from_background": sorted(sets["benchmark"] - sets["background"]), "discovery_absent_from_background": sorted(sets["discovery"] - sets["background"]), "unresolved": sorted(item.canonical_identity for item in unresolved)}
    report["counts"] = {key: len(value) for key, value in report.items() if isinstance(value, list)}; report["overlap_report_id"] = _id("tuo", report); return report


def _write_json(path: Path, value: Any) -> None: path.write_text(canonical_json(value) + "\n", encoding="utf-8", newline="")
def _write_tsv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    fields = sorted({key for row in rows for key in row}) or ["canonical_identity"]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, delimiter="\t", extrasaction="ignore"); writer.writeheader()
        for row in sorted(rows, key=lambda item: str(item.get("canonical_identity", ""))): writer.writerow({key: json.dumps(value, sort_keys=True) if isinstance(value, (list, dict)) else value for key, value in row.items()})


def freeze_universes(benchmark_path: Path, discovery_path: Path, policy_path: Path, background_gene_index: Path, context: Mapping[str, Any], output_dir: Path) -> TargetUniverseFreezeManifest:
    leakage_audit(context)
    benchmark, benchmark_entries = load_benchmark(benchmark_path); policy = load_policy(policy_path); discovery, rejected = load_discovery(discovery_path, policy, benchmark)
    background, malformed = load_background(background_gene_index, _text(context.get("release_manifest_id")), _text(context.get("canonical_mapping_version")))
    unresolved = tuple(rejected) + tuple(TargetUniverseEntry(FORMAT_VERSION, row.get("original_source_label", ""), row.get("original_source_label", "malformed"), "discovery", (), ("other_unresolved",), inclusion_status="unresolved", rejection_reason="malformed background gene-index column") for row in malformed)
    overlap = overlap_report(benchmark, discovery, background, unresolved); unresolved_payload = [item.to_dict() for item in unresolved]
    manifest = TargetUniverseFreezeManifest(_text(context.get("context_identity")), _text(context.get("disease_identity")), benchmark.universe_id, discovery.universe_id, background.universe_id, (policy.policy_id, background.construction_policy_id or ""), tuple(sorted({source.dataset_version for entry in discovery.entries for source in entry.inclusion_sources} | {_text(context.get("release_manifest_id"))})), _text(context.get("canonical_mapping_version")), overlap["overlap_report_id"], _id("tur", unresolved_payload), ("Freeze is reproducibility metadata, not validation, benchmark success, or clinical utility.",))
    output_dir.mkdir(parents=True, exist_ok=True)
    _write_tsv(output_dir / "benchmark_universe.tsv", [item.to_dict() for item in benchmark_entries]); _write_tsv(output_dir / "discovery_universe.tsv", [item.to_dict() for item in discovery.entries]); _write_tsv(output_dir / "background_universe.tsv", [item.to_dict() for item in background.entries]); _write_tsv(output_dir / "unresolved_targets.tsv", unresolved_payload); _write_tsv(output_dir / "rejected_targets.tsv", [item.to_dict() for item in rejected]); _write_json(output_dir / "universe_overlap.json", overlap); _write_json(output_dir / "leakage_audit.json", leakage_audit({"context": context, "policy": policy.to_dict(), "discovery_sources": read_tsv(discovery_path)})); _write_json(output_dir / "universe_freeze_manifest.json", {**manifest.to_dict(), "freeze_id": manifest.freeze_id})
    return manifest

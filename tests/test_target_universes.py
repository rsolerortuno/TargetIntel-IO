"""Offline contracts for v0.5.0 target-universe freezing."""
from __future__ import annotations
import json
from pathlib import Path
import pytest
import yaml
from targetintel.functional_dependency.target_universes import (
    FORMAT_VERSION, InclusionSourceRecord, TargetUniverse, TargetUniverseEntry,
    RESISTANCE_AXES, freeze_universes, leakage_audit, load_benchmark,
    load_discovery, load_policy,
)

ROOT = Path(__file__).parent / "fixtures" / "depmap" / "universes"
CONTEXT_ROOT = Path(__file__).parents[1] / "contexts" / "melanoma_anti_pd1"

def test_entry_identity_is_order_independent_and_type_sensitive() -> None:
    source = InclusionSourceRecord("resistance_axis", "r1", "v1", "exact")
    a = TargetUniverseEntry(FORMAT_VERSION, "BRAF", "symbol:BRAF|entrez:673", "discovery", (source,), ("melanoma_plasticity", "other_unresolved"))
    b = TargetUniverseEntry(FORMAT_VERSION, "BRAF", "symbol:BRAF|entrez:673", "discovery", (source,), ("other_unresolved", "melanoma_plasticity"))
    c = TargetUniverseEntry(FORMAT_VERSION, "BRAF", "symbol:BRAF|entrez:673", "benchmark", (source,), ("other_unresolved", "melanoma_plasticity"))
    assert a.entry_id == b.entry_id and a.entry_id != c.entry_id
    with pytest.raises((TypeError, AttributeError)):
        a.inclusion_sources += (source,)

def test_benchmark_integrity_and_discovery_policy_are_controlled() -> None:
    benchmark, entries = load_benchmark(ROOT / "benchmark.tsv")
    assert len(entries) == 4 and {item.partition for item in entries} == {"development", "holdout"}
    policy = load_policy(ROOT / "discovery_policy.json")
    assert policy.benchmark_union_required and benchmark.universe_type == "benchmark"
    with pytest.raises(ValueError, match="forbidden"):
        leakage_audit({"outer": {"depmap_gene_effect": -1}})
    with pytest.raises(ValueError, match="duplicate canonical"):
        TargetUniverse("discovery", "v1", (entries[0].entry, entries[0].entry))

def test_fixture_freeze_is_deterministic_and_has_no_scores(tmp_path: Path) -> None:
    index = tmp_path / "gene_index.tsv"
    index.write_text("dataset_role\tsource_column_index\toriginal_source_label\tparsed_symbol\tparsed_entrez_identifier\tparser_status\tcanonical_identity\tlimitation\ncrispr_gene_effect\t1\tBRAF (673)\tBRAF\t673\tparsed\tsymbol:BRAF|entrez:673\t\ncrispr_gene_effect\t2\tBAD\t\t\tmalformed\t\t\n")
    context = json.loads((ROOT / "context.json").read_text())
    first = freeze_universes(ROOT / "benchmark.tsv", ROOT / "discovery_sources.tsv", ROOT / "discovery_policy.json", index, context, tmp_path / "one")
    second = freeze_universes(ROOT / "benchmark.tsv", ROOT / "discovery_sources.tsv", ROOT / "discovery_policy.json", index, context, tmp_path / "two")
    assert first.freeze_id == second.freeze_id
    assert (tmp_path / "one" / "universe_freeze_manifest.json").read_bytes() == (tmp_path / "two" / "universe_freeze_manifest.json").read_bytes()
    assert "score" not in (tmp_path / "one" / "universe_freeze_manifest.json").read_text().lower()


def test_context_artifacts_freeze_the_audited_benchmark_and_reuse_axis_keys() -> None:
    benchmark, entries = load_benchmark(CONTEXT_ROOT / "benchmarks" / "benchmark_v1.tsv")
    policy = load_policy(CONTEXT_ROOT / "universes" / "discovery_policy_v1.json")
    discovery, rejected = load_discovery(
        CONTEXT_ROOT / "universes" / "discovery_sources_v1.tsv", policy, benchmark
    )
    configured_axes = set(yaml.safe_load(
        (Path(__file__).parents[1] / "configs" / "resistance_axes.yaml").read_text()
    ))
    assert len(entries) == 56
    assert {entry.entry.canonical_identity for entry in entries} <= {
        entry.canonical_identity for entry in discovery.entries
    }
    assert not rejected
    assert RESISTANCE_AXES == configured_axes | {"other_unresolved"}


def test_context_benchmark_preserves_unmapped_axis_assignments() -> None:
    """Genes absent from the curated ontology retain the explicit unresolved axis."""
    _, entries = load_benchmark(CONTEXT_ROOT / "benchmarks" / "benchmark_v1.tsv")
    axes_by_symbol = {
        item.entry.original_identifier: item.entry.resistance_axes
        for item in entries
    }
    assert {
        symbol: axes_by_symbol[symbol]
        for symbol in ("BAP1", "TP53", "CDK4", "KIT", "MAP2K2", "MITF", "TERT")
    } == {
        "BAP1": ("other_unresolved",),
        "TP53": ("other_unresolved",),
        "CDK4": ("other_unresolved",),
        "KIT": ("other_unresolved",),
        "MAP2K2": ("other_unresolved",),
        "MITF": ("other_unresolved",),
        "TERT": ("other_unresolved",),
    }

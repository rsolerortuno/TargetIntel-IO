"""Release-hardening documentation regressions."""

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).parents[1]
SEQUENCE = (
    "v0.2.0 — Common Evidence Layer",
    "v0.3.0 — Grounded Literature Copilot and provider-agnostic LLM integration",
    "v0.4.0 — Target feasibility and expanded Open Targets integration",
    "v0.5.0 — DepMap/CRISPR functional dependency",
    "v0.6.0 — Single-cell and spatial context",
    "v0.7.0 — Clinical-response research model",
    "v0.8.0 — De novo target discovery and knowledge graph",
    "v1.0.0 — Multitumor target-intelligence platform",
)


def test_release_docs_and_roadmap_are_present_and_consistent() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    roadmap = (ROOT / "docs/ROADMAP_2_0.md").read_text(encoding="utf-8")
    assert len(readme.splitlines()) <= 360
    assert "v0.2.0 is infrastructure and report decoration" in readme
    assert "production LLM extractor" in readme
    for entry in SEQUENCE:
        assert entry.replace(" — ", " ") in readme
        version, label = entry.split(" — ", maxsplit=1)
        assert version in roadmap and label in roadmap
    assert (ROOT / "CHANGELOG.md").is_file()
    assert (ROOT / "docs/releases/v0.2.0.md").is_file()
    assert (ROOT / "docs/specs/v0.3.0_grounded_literature_copilot.md").is_file()


def test_roadmap_preserves_long_term_design_anchors() -> None:
    roadmap = (ROOT / "docs/ROADMAP_2_0.md").read_text(encoding="utf-8")
    required_anchors = (
        "EvidenceItem and literature-processing architecture",
        '\"target_id\": \"MOCK_TARGET\"',
        "PMID, PMCID, DOI",
        "known_drug_count",
        "small_molecule_tractability",
        "depmap_mean_gene_effect_melanoma",
        "depmap_lineage_selectivity",
        "malignant_expression_mean",
        "ligand_receptor_interaction_score",
        "Hugo/GSE78220",
        "Riaz/GSE91061",
        "train candidate model -> lock specification",
        "TARGET associated_with DISEASE",
        "configs/contexts/",
        "Confidence is a reportable decomposition",
        "Final Hybrid AI Architecture",
        "Core design principles",
        "Independent evidence is not record count",
    )
    for anchor in required_anchors:
        assert anchor in roadmap

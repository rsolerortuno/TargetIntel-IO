# TargetIntel-IO roadmap

TargetIntel-IO retains a deterministic, transparent baseline for anti-PD-1-resistant melanoma. Optional evidence capabilities must preserve source provenance, keep observations separate from interpretation, and never silently change deterministic scores, roles, rankings, benchmark results, or sensitivity outputs.

The framework is for hypothesis generation and target triage. It is not clinical validation, a qualified biomarker system, a validated therapeutic-target system, medical advice, or proof of causality. Missing evidence is not negative evidence, and the internal benchmark is not independent biological or clinical validation.

## Release sequence

| Version | Focus |
|---|---|
| v0.2.0 | Common Evidence Layer |
| v0.3.0 | Grounded Literature Copilot and provider-agnostic LLM integration |
| v0.4.0 | Target feasibility and expanded Open Targets integration |
| v0.5.0 | DepMap/CRISPR functional dependency |
| v0.6.0 | Single-cell and spatial context |
| v0.7.0 | Clinical-response research model |
| v0.8.0 | De novo target discovery and knowledge graph |
| v1.0.0 | Multitumor target-intelligence platform |

## v0.2.0 — Common Evidence Layer

Completed infrastructure: immutable typed evidence contracts; intrinsic and semantic validation; provenance, lineage, evidence-family and exact-duplicate controls; DuckDB storage and deterministic Parquet snapshots; retrieval-attempt auditing; Europe PMC retrieval; deterministic mock extraction; literal quotation and computed-support verification; and optional, post-ranking Markdown and HTML evidence-card decoration.

Read-only reporting validates the stored schema without DDL or DML. An explicitly supplied missing, directory, malformed, or incompatible evidence-store path fails clearly. The fabricated offline demo exercises the boundary without real scientific claims.

v0.2.0 does not contain a production literature copilot or production LLM extraction. It is evidence infrastructure and report decoration, not clinical validation.

## v0.3.0 — Grounded Literature Copilot and provider-agnostic LLM integration

This phase defines an operational evidence CLI around retrieved source text and
provider-neutral extractor interfaces. Extractors may propose structured
observations, but must not generate PMIDs, DOIs, citations, identifiers, or
numerical results. Every exposed literature observation requires an exact
quotation and document location, deterministic validation, and citation
verification before it can become a finalized `EvidenceItem`.

The processing design separates query expansion and relevance ranking from
pagination, full-text retrieval, and section-aware extraction. It records
prompt, provider, model, version, retry, timeout, failure, and non-execution
provenance. An extractor proposes records, a critic identifies unsupported or
limiting claims, and a writer synthesizes target-level supportive,
contradictory, limiting, and missing evidence from finalized verified items
only. Failed and rejected records remain visible in audit reports. Offline
fake-provider tests and a manually reviewed extraction-quality benchmark are
required before any scientific publication, which remains subject to human
review. Citation verification, source verification, computation verification,
and scientific review are separate future controls.

This optional layer cannot alter deterministic roles, scores, rankings,
benchmark results, sensitivity outputs, or ranking weights.

## v0.4.0 — Target feasibility and expanded Open Targets integration

This phase expands versioned Open Targets inputs and evaluates target
feasibility separately from association strength. Candidate features may
include modality fit, tissue and safety context, known drug and target-class
information, tractability, pathway context, and contradictory evidence. The
design must preserve uncertainty and the distinction between a therapeutic
target, biomarker, resistance mechanism, immune-context marker,
tumor-intrinsic driver, and poor direct target; it does not imply that any
association is causal or clinically actionable.

## v0.5.0 — DepMap/CRISPR functional dependency

This phase investigates whether versioned functional-dependency data can add
carefully scoped context to candidate review. Questions include whether a
dependency is lineage- or genotype-specific, whether it is consistent across
models, how assay and model-system limitations affect interpretation, and
whether a dependency is therapeutically relevant rather than merely
essential. Candidate features include dependency magnitude, replicate and
screen consistency, co-dependency, genomic context, expression context, and
normal-tissue limitations. Numerical integration is deferred until its
provenance, transformations, and validation are specified.

## v0.6.0 — Single-cell and spatial context

This phase studies which cell populations express a candidate, how state,
compartment, and treatment context shape that expression, and whether spatial
proximity supports a mechanistic hypothesis. Candidate features include cell
type and state, tumor-versus-immune compartment, abundance, neighborhood,
co-localization, and pre/post-treatment context. Batch effects, cohort
composition, annotation uncertainty, and the non-equivalence of expression
and therapeutic action must remain explicit.

## v0.7.0 — Clinical-response research model

This research phase designs clinical-cohort and external-validation strategy,
not a diagnostic or treatment-recommendation system. It must predefine cohort
eligibility, endpoints, treatment exposure, confounding controls, missing-data
handling, temporal splits, calibration, and held-out external evaluation.
Candidate response features require clear provenance and population scope;
observational association does not establish causal response prediction.

## v0.8.0 — De novo target discovery and knowledge graph

This phase explores de novo hypotheses using a provenance-preserving knowledge
graph. The graph should retain source records, versioned entities and edges,
evidence families, contradictions, negative or missing evidence, and the
transformations that produced derived links. Discovery candidates must remain
separate from established targets and be presented as auditable hypotheses.
Confidence should be decomposed into evidence quality, source independence,
biological coherence, model applicability, and uncertainty rather than
collapsed into an unsupported claim of validation.

## v1.0.0 — Multitumor target-intelligence platform

The long-term platform generalizes through disease and treatment context
packs: explicit ontologies, input versions, resistance programs, modalities,
benchmark boundaries, and reporting templates for each supported context.
Its hybrid-AI architecture keeps deterministic classification and ranking
separate from optional evidence retrieval, validation, critic, and writer
components. The evidence layer supplies traceable observations; the baseline
remains the reproducible decision scaffold; human review controls scientific
publication. Multitumor support is not implied until each context pack has
defined validation and scope.

## Preserved long-term technical design

### v0.3.0 EvidenceItem and literature-processing architecture

The common layer remains the hand-off boundary for future literature processing. A finalized record has source-linked, typed content rather than an unbounded model narrative:

```json
{
  "target_id": "MOCK_TARGET",
  "evidence_type": "literature_observation",
  "claim": "A source-linked observation",
  "source_identifier": "PMID:00000000",
  "quotation": "Exact source span",
  "document_location": "Results, paragraph 2",
  "provenance": [{"step": "retrieval", "version": "recorded"}]
}
```

The identifiers and claim are illustrative placeholders, not scientific evidence. The operational flow is deliberately bounded:

```text
query expansion -> retrieved source text -> section-aware extraction
    -> intrinsic/semantic validation -> literal citation verification
    -> final EvidenceItem -> family/duplicate controls -> report decoration
                              \-> rejected/failed audit record
```

Hallucination controls require that a model never invent a PMID, PMCID, DOI, source citation, quoted span, document location, numerical result, or source metadata. A proposed record is rejected unless its identifier is retrieved, its quotation is literal source text at the recorded location, and its typed fields and provenance pass deterministic validation. The extractor proposes bounded records, the critic flags unsupported, contradictory, or limiting support, and the writer uses finalized verified records only.

### v0.4.0 feasibility feature design

Potential versioned inputs must remain independently inspectable rather than become a hidden feasibility score. Candidate fields include `association_score_by_source`, `genetic_association_score`, `somatic_mutation_score`, `known_drug_count`, `maximum_clinical_phase`, `small_molecule_tractability`, `antibody_tractability`, `protac_tractability`, `chemical_probe_available`, `safety_signal_count`, `normal_tissue_risk`, `clinical_precedence`, `target_class`, and `pathway_context`. Their availability, source release, transformation, and missingness must be reported; a field is not proof that a target is feasible, causal, safe, or clinically actionable.

### v0.5.0 functional-dependency questions and candidate features

The design asks whether dependency is selective in melanoma, stable across screens and replicates, related to a genomic or transcriptional state, associated with BRAF, NRAS, or NF1 status, and separable from universal essentiality. Candidate fields include `depmap_mean_gene_effect_melanoma`, `depmap_fraction_dependent_melanoma`, `depmap_lineage_selectivity`, `depmap_pan_cancer_dependency`, `depmap_common_essential_flag`, `depmap_expression_dependency_correlation`, `depmap_braf_mutant_dependency`, `depmap_nras_mutant_dependency`, `depmap_nf1_mutant_dependency`, `depmap_screen_consistency`, `depmap_replicate_count`, and `depmap_codependency_score`. They are research context, not numerical evidence for a treatment recommendation.

### v0.6.0 cellular-context questions and candidate features

The analysis design asks which malignant, immune, Treg, myeloid, fibroblast, and stromal states express a candidate; whether expression changes in resistant-versus-sensitive or pretreatment-versus-on-treatment comparisons; and whether spatial neighborhoods support only a testable mechanistic hypothesis. Candidate fields include `malignant_expression_mean`, `immune_expression_mean`, `treg_specificity`, `myeloid_specificity`, `fibroblast_specificity`, `tumor_normal_specificity`, `patient_level_consistency`, `cell_state_specificity`, `tumor_immune_ratio`, `spatial_neighborhood_enrichment`, `ligand_receptor_interaction_score`, and `pre_post_treatment_change`. Cohort, annotation, assay, and batch provenance must accompany every field.

### v0.7.0 cohort and external-validation design

Candidate research cohorts include Hugo/GSE78220, Riaz/GSE91061, and Gide datasets only where their terms, treatment context, endpoints, and provenance allow responsible use. The intended design is prospective in its discipline, not in its claim:

```text
eligible discovery cohort -> train candidate model -> lock specification
    -> held-out external cohort -> calibration and error review
```

No cohort is a substitute for clinical validation. Population shift, small sample size, treatment heterogeneity, confounding, label definition, and missing data must be visible in the report.

### v0.8.0 knowledge-graph architecture and confidence decomposition

Planned node types include `Target`, `Disease`, `Drug`, `Pathway`, `Publication`, `Evidence`, `Dataset`, `Experiment`, `CellState`, and `Cohort`. Planned typed edges include `TARGET associated_with DISEASE`, `DRUG modulates TARGET`, `TARGET participates_in PATHWAY`, `CLAIM supported_by PUBLICATION`, `TARGET has_safety_signal EVENT`, `EVIDENCE derived_from DATASET`, `EVIDENCE supports TARGET`, `EVIDENCE contradicts TARGET`, and `TARGET expressed_in CellState`. Initial interpretable methods are network propagation, similarity to known targets, weighted evidence integration, clustering of target profiles, positive–unlabeled learning, and interpretable learning-to-rank; graph neural networks, embeddings, and link prediction remain later extensions. Every edge must retain source identifiers, release/version, transformation history, family identity, and support status.

Confidence is a reportable decomposition, never a substitute for validation:

| Dimension | Question |
|---|---|
| Data completeness | Are the relevant inputs present and scoped? |
| Evidence strength | How directly and reliably do sources support the observation? |
| Evidence independence | Are records independent, rather than duplicates or one family? |
| Decision robustness | Does the result persist under defined deterministic sensitivity checks? |
| LLM extraction confidence | Did a future model proposal survive source-linked verification? |

The last dimension characterizes an extraction process, not scientific truth; it must not silently influence baseline scoring.

### v1.0.0 Context packs and Final Hybrid AI Architecture

Each supported context needs an explicit, versioned pack rather than a melanoma label applied to a different disease:

```text
configs/contexts/
  anti_pd1_resistant_melanoma.yaml
  <future_context>.yaml
```

```yaml
context_id: anti_pd1_resistant_melanoma
ontology_id: MONDO_0005105
therapy: anti_PD1
drugs: [nivolumab, pembrolizumab]
resistance_programs: [versioned_program_ids]
modalities: [antibody, small_molecule]
relevant_cell_types: [malignant_cell, exhausted_T_cell, macrophage, Treg, fibroblast]
clinical_endpoints: [response, progression_free_survival, overall_survival]
benchmark_boundary: internal_hypothesis_generation_only
report_template: target_triage
```

The final hybrid architecture assigns bounded responsibilities:

| Component | Technology role |
|---|---|
| Deterministic baseline | Versioned features, stable roles, intent rankings, benchmark and sensitivity outputs |
| Evidence services | Retrieval records, typed EvidenceItems, validation, duplicate/family controls, immutable storage |
| Optional model services | Provider-neutral extraction, critic, and grounded writer proposals |
| Functional genomics | Versioned dependency statistics, biological networks, and scoped learned models |
| Cellular and spatial analysis | Specialized omics methods with cell- and region-level provenance |
| Discovery and response research | Interpretable learning-to-rank and calibrated research models, with external evaluation |
| Human review | Scientific interpretation, publication decisions, scope and safety review |

### Core design principles

1. Evidence before interpretation: observations are source-linked before narrative synthesis.
2. Traceability fields: source identifier, release, retrieval date, quotation, location, transformation, hash, and provenance remain available for audit.
3. Independent evidence is not record count: exact duplicates and related evidence families cannot be presented as multiple independent confirmations.
4. Deterministic isolation: optional evidence and model layers cannot alter stable roles, scores, rankings, benchmark labels, or sensitivity outputs.
5. Human review: no automated output is clinical advice, biomarker qualification, therapeutic-target validation, or a scientific publication.

## Cross-phase guardrails and exclusions

Production extraction, expanded retrieval, new validation vocabularies or
migrations, production audit reporting, external scientific validation, and
clinical validation remain separate, explicitly scoped future work. These
releases do not include target-feasibility scoring in v0.3.0, automatic
ranking-weight changes, graph neural networks, clinical recommendations, or
multitumor production support before their designated phases.

# TGFBR1 — DepMap research-preview discovery identity

This identity is part of the research-preview discovery universe and is not part of the authoritative productive baseline.

## Functional dependency — DepMap Public 26Q1

### Coverage

- **Profile available:** yes
- **Coverage status:** sufficient_complete_coverage
- **Total model count:** 2154
- **Context model count:** 56
- **Reference model count:** 2098
- **Available context observations:** 56
- **Available reference observations:** 1152
- **Coverage fraction:** 1.0
- **Missing-value state:** target_resolved_both_matrices
- **Unavailable reason:** not reported

### Dependency profile

- **Gene-effect summary:** {"available":true,"first_quartile":-0.11823496925689045,"interquartile_range":0.1815436279172879,"maximum":0.43900246007390836,"mean":-0.06367073288882538,"measured_model_count":56,"median":-0.04561856834087192,"minimum":-1.1646984150993804,"missing_fraction":0.0,"missing_model_count":0,"third_quartile":0.06330865866039743,"threshold_fractions":[],"total_model_count":56}
- **Dependency-probability summary:** {"available":true,"first_quartile":0.009869685591532288,"interquartile_range":0.05375446023576694,"maximum":0.9941992212349525,"mean":0.0798662849461864,"measured_model_count":56,"median":0.03221306181112013,"minimum":0.0002895613022257384,"missing_fraction":0.0,"missing_model_count":0,"third_quartile":0.06362414582729922,"threshold_fractions":[{"denominator":56,"fraction":0.03571428571428571,"numerator":2,"threshold":0.5},{"denominator":56,"fraction":0.017857142857142856,"numerator":1,"threshold":0.8}],"total_model_count":56}
- **Context-versus-reference comparison:** {"context_minus_pan_cancer":{"dependency_probability_median":-0.027031213832151124,"dependency_probability_threshold_fractions":[{"context_fraction":0.03571428571428571,"difference":-0.04623935666982025,"pan_cancer_fraction":0.08195364238410596,"threshold":0.5},{"context_fraction":0.017857142857142856,"difference":-0.0152554399243141,"pan_cancer_fraction":0.033112582781456956,"threshold":0.8}],"gene_effect_mean":0.07847455721250848,"gene_effect_median":0.07036460916164552},"dependency_probability_context_minus_non_context_median":-0.029586105478545344,"dependency_probability_context_minus_non_context_threshold_fractions":[{"context_fraction":0.03571428571428571,"difference":-0.04848710317460318,"non_context_fraction":0.0842013888888889,"threshold":0.5},{"context_fraction":0.017857142857142856,"difference":-0.015997023809523808,"non_context_fraction":0.033854166666666664,"threshold":0.8}],"direction":"Negative gene-effect context-minus-reference values indicate stronger model dependency signal in the context group.","gene_effect_context_minus_non_context_mean":0.08228929263256096,"gene_effect_context_minus_non_context_median":0.07618939226126986}
- **Selectivity:** {"available":true,"direction":"100 means a stronger (more negative median gene-effect) context signal than most eligible lineages.","eligible_lineage_count":28,"value":11.11111111111111}
- **Dependency interpretation state:** valid

### Integration

- **Baseline rank:** not reported
- **Dependency-aware candidate rank:** not reported
- **Rank delta:** not reported
- **Rank-delta convention:** dependency-aware candidate rank minus baseline rank.
- **Negative rank delta:** movement toward a lower numerical rank.
- **Integration state:** blocked_insufficient_evidence
- **Baseline preserved:** yes
- **Production activation enabled:** disabled
- **Approved authorization emitted:** not emitted
- **Candidate activation readiness:** blocked
- **Human review required:** required

### Release provenance

- **Evidence ID:** `drep_8024c3f1a166237bfd323397a878e35e9a91c24effde75af6a2a2b954766b2da`
- **Release identifier:** `DepMap_Public_26Q1`
- **Release manifest ID:** `dmrm_08d15741ac2297df953346ff257dec05feb0b754a62ae6a9f56573e11801c5b1`
- **Configuration ID:** `v050rc_fe68644624acd4b72aaf289baa9380c07f30d26c3271923ba81540f9b91e37b6`
- **Scientific closure identity:** `v050closure_e57fa135ff266078d2170bf2a34df094f7888e7ce6002783c75f6a583690a3a4`
- **Context identity:** `melanoma_anti_pd1:v1`
- **Canonical gene identity:** `symbol:TGFBR1|entrez:7046`
- **Contract format version:** `v1`
- **Portable source artifacts:** `candidate_overlay.tsv`, `selected_target_profiles.tsv`

### Limitations

- Acral and drug-adapted models are excluded from the primary profile and retained separately.
- Baseline: unchanged 300-target TargetIntel antibody-IO ranking.
- Benchmark canonical identities were reconciled against the DepMap Public 26Q1 gene index without changing benchmark membership.
- DepMap Public 26Q1 cell-line dependency evidence.
- Dependency is treated as explanatory evidence, not as clinical validation.
- Descriptive real-release aggregate evidence only; no therapeutic, clinical, safety, or causal conclusion.
- Multi-axis annotations are represented as pipe-separated controlled resistance-axis values.
- No automatic target activation or release.
- No clinical anti-PD-1 response inference.
- Primary context contains 56 reviewed cutaneous melanoma cell-line models.
- Primary context: 56 reviewed cutaneous melanoma models.
- Thresholds were fixed before inspecting benchmark outcomes.
- Unmapped resistance-axis annotations are represented by the controlled value other_unresolved.
- DepMap cell-line dependency is not clinical anti-PD-1 response evidence.
- Absence of tumor-cell dependency does not invalidate an immune target.
- Broad dependency may reflect general essentiality.
- Cell lines do not reproduce the complete tumor microenvironment.
- Candidate activation requires explicit human review.

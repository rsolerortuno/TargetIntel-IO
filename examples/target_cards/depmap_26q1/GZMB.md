# GZMB — DepMap research-preview discovery identity

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

- **Gene-effect summary:** {"available":true,"first_quartile":-0.17244025699697157,"interquartile_range":0.2215586500992243,"maximum":0.3725292682983529,"mean":-0.043664638800793,"measured_model_count":56,"median":-0.06917978710613715,"minimum":-0.31096479898487983,"missing_fraction":0.0,"missing_model_count":0,"third_quartile":0.04911839310225271,"threshold_fractions":[],"total_model_count":56}
- **Dependency-probability summary:** {"available":true,"first_quartile":0.009710803170775517,"interquartile_range":0.08752127492675235,"maximum":0.246250297339304,"mean":0.05926205677955833,"measured_model_count":56,"median":0.034480980287158486,"minimum":0.0007627617070437107,"missing_fraction":0.0,"missing_model_count":0,"third_quartile":0.09723207809752787,"threshold_fractions":[{"denominator":56,"fraction":0.0,"numerator":0,"threshold":0.5},{"denominator":56,"fraction":0.0,"numerator":0,"threshold":0.8}],"total_model_count":56}
- **Context-versus-reference comparison:** {"context_minus_pan_cancer":{"dependency_probability_median":-0.01345836150324789,"dependency_probability_threshold_fractions":[{"context_fraction":0.0,"difference":-0.03145695364238411,"pan_cancer_fraction":0.03145695364238411,"threshold":0.5},{"context_fraction":0.0,"difference":-0.0024834437086092716,"pan_cancer_fraction":0.0024834437086092716,"threshold":0.8}],"gene_effect_mean":0.05748615344446486,"gene_effect_median":0.02104996878975203},"dependency_probability_context_minus_non_context_median":-0.01427025841020696,"dependency_probability_context_minus_non_context_threshold_fractions":[{"context_fraction":0.0,"difference":-0.03298611111111111,"non_context_fraction":0.03298611111111111,"threshold":0.5},{"context_fraction":0.0,"difference":-0.0026041666666666665,"non_context_fraction":0.0026041666666666665,"threshold":0.8}],"direction":"Negative gene-effect context-minus-reference values indicate stronger model dependency signal in the context group.","gene_effect_context_minus_non_context_mean":0.06028061923690404,"gene_effect_context_minus_non_context_median":0.021472073888966117}
- **Selectivity:** {"available":true,"direction":"100 means a stronger (more negative median gene-effect) context signal than most eligible lineages.","eligible_lineage_count":28,"value":14.814814814814815}
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

- **Evidence ID:** `drep_151ecdb83f44b504f40cc23529671c3a71580ccd555c775989d15d4c13db48d7`
- **Release identifier:** `DepMap_Public_26Q1`
- **Release manifest ID:** `dmrm_08d15741ac2297df953346ff257dec05feb0b754a62ae6a9f56573e11801c5b1`
- **Configuration ID:** `v050rc_fe68644624acd4b72aaf289baa9380c07f30d26c3271923ba81540f9b91e37b6`
- **Scientific closure identity:** `v050closure_e57fa135ff266078d2170bf2a34df094f7888e7ce6002783c75f6a583690a3a4`
- **Context identity:** `melanoma_anti_pd1:v1`
- **Canonical gene identity:** `symbol:GZMB|entrez:3002`
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

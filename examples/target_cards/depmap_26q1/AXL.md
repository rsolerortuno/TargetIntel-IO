# AXL — DepMap research-preview discovery identity

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

- **Gene-effect summary:** {"available":true,"first_quartile":-0.09669271225359513,"interquartile_range":0.13838293442208938,"maximum":0.33269592966644873,"mean":-0.05402248348828266,"measured_model_count":56,"median":-0.05461535624294615,"minimum":-0.591523976802867,"missing_fraction":0.0,"missing_model_count":0,"third_quartile":0.041690222168494245,"threshold_fractions":[],"total_model_count":56}
- **Dependency-probability summary:** {"available":true,"first_quartile":0.01321277007165553,"interquartile_range":0.047403672929686676,"maximum":0.5937823231403992,"mean":0.06668973321292734,"measured_model_count":56,"median":0.03594859224302639,"minimum":0.0021112287349255585,"missing_fraction":0.0,"missing_model_count":0,"third_quartile":0.0606164430013422,"threshold_fractions":[{"denominator":56,"fraction":0.017857142857142856,"numerator":1,"threshold":0.5},{"denominator":56,"fraction":0.0,"numerator":0,"threshold":0.8}],"total_model_count":56}
- **Context-versus-reference comparison:** {"context_minus_pan_cancer":{"dependency_probability_median":0.00841929504751433,"dependency_probability_threshold_fractions":[{"context_fraction":0.017857142857142856,"difference":0.005439924314096499,"pan_cancer_fraction":0.012417218543046357,"threshold":0.5},{"context_fraction":0.0,"difference":-0.0033112582781456954,"pan_cancer_fraction":0.0033112582781456954,"threshold":0.8}],"gene_effect_mean":-0.009449488770846413,"gene_effect_median":-0.028192670549813503},"dependency_probability_context_minus_non_context_median":0.00855861376300604,"dependency_probability_context_minus_non_context_threshold_fractions":[{"context_fraction":0.017857142857142856,"difference":0.005704365079365078,"non_context_fraction":0.012152777777777778,"threshold":0.5},{"context_fraction":0.0,"difference":-0.003472222222222222,"non_context_fraction":0.003472222222222222,"threshold":0.8}],"direction":"Negative gene-effect context-minus-reference values indicate stronger model dependency signal in the context group.","gene_effect_context_minus_non_context_mean":-0.009908838919429161,"gene_effect_context_minus_non_context_median":-0.029581425927257432}
- **Selectivity:** {"available":true,"direction":"100 means a stronger (more negative median gene-effect) context signal than most eligible lineages.","eligible_lineage_count":28,"value":77.77777777777777}
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

- **Evidence ID:** `drep_4998e8d48eb17bd589670b508f8684da20ab3963cc8de33d05845accbfaee6be`
- **Release identifier:** `DepMap_Public_26Q1`
- **Release manifest ID:** `dmrm_08d15741ac2297df953346ff257dec05feb0b754a62ae6a9f56573e11801c5b1`
- **Configuration ID:** `v050rc_fe68644624acd4b72aaf289baa9380c07f30d26c3271923ba81540f9b91e37b6`
- **Scientific closure identity:** `v050closure_e57fa135ff266078d2170bf2a34df094f7888e7ce6002783c75f6a583690a3a4`
- **Context identity:** `melanoma_anti_pd1:v1`
- **Canonical gene identity:** `symbol:AXL|entrez:558`
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

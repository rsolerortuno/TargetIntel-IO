# Portable DepMap report snapshot

This repository-safe derived snapshot records `DepMap_Public_26Q1` for melanoma anti-PD-1 context (`melanoma_anti_pd1:v1`). Configuration identity: `v050rc_fe68644624acd4b72aaf289baa9380c07f30d26c3271923ba81540f9b91e37b6`. Release manifest identity: `dmrm_08d15741ac2297df953346ff257dec05feb0b754a62ae6a9f56573e11801c5b1`. Scientific closure identity: `v050closure_e57fa135ff266078d2170bf2a34df094f7888e7ce6002783c75f6a583690a3a4`.

The original productive baseline contains 300 genes and remains unchanged. The discovery universe contains 331 identities; 18,531 genes were used only as background, and no 18,531-gene productive ranking was generated. Production activation is disabled and human review is mandatory.

DepMap cell-line dependency is not clinical anti-PD-1 response evidence. Absence of tumor-cell dependency does not invalidate an immune target. General dependency may reflect broad essentiality, and cell lines do not reproduce the full tumor microenvironment. Full matrices and `dependency_profiles.jsonl` are excluded.

Files: `release_summary.json` records validated closure state; the three Markdown reports preserve sanitized aggregate reports; `candidate_overlay.tsv` and `dependency_profile_summary.tsv` are derived aggregate tables; `selected_target_profiles.tsv` contains only requested descriptive profiles; `checksums.json` verifies the other eight files.

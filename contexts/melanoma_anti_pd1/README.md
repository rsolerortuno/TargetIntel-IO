# Melanoma anti-PD-1 context package

Status: `development`. This package contains the frozen 56-symbol internal
benchmark in `benchmarks/benchmark_v1.tsv` and pre-DepMap discovery seed
records in `universes/discovery_sources_v1.tsv`. Both artifacts are derived
only from the existing repository curation: `configs/benchmark_targets.yaml`
and `configs/resistance_axes.yaml`. The policy in
`universes/discovery_policy_v1.json` requires benchmark union so all benchmark
genes remain available for a later evaluation step.

The current discovery artifact has 66 genes after the deterministic benchmark
union. It is intentionally below the 300–1,000-gene advisory range: adding
unsupported genes to meet that range would not be reproducible curation.
Expansion requires separately reviewed, pre-DepMap source records. This package
contains no raw DepMap or patient data and makes no claim of clinical,
therapeutic, or benchmark validation.

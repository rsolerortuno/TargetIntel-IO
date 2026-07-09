# Changelog

All notable changes to TargetIntel-IO are documented in this file.

## [0.1.1] - 2026-07-09

### Added

- One-weight-at-a-time scoring sensitivity analysis with `-20%` and `+20%`
  perturbations followed by weight renormalization.
- Ranking-stability metrics including Spearman correlation, top-k Jaccard
  similarity, top-k retention, and per-target rank variation.
- Versioned sensitivity-analysis snapshot with machine-readable outputs,
  SHA-256 manifest, visualization, and regression tests.
- Quantitative README limitations grounded in the committed benchmark and
  sensitivity snapshots.
- Complete runtime dependency declarations in `pyproject.toml` and
  `environment.yml`.
- Exact Python 3.11 dependency lockfile with transitive dependencies and
  package hashes.
- CI installation from the locked dependency environment.

### Sensitivity results

Across 42 one-weight-at-a-time perturbation scenarios:

- all therapeutic-intent profiles retained 100% of their baseline top five;
- worst-case top-10 retention was 90% for antibody/IO, 100% for biomarker,
  and 90% for small-molecule ranking;
- worst-case top-20 retention was 100%, 95%, and 100%, respectively;
- minimum Spearman rank correlation was 0.9852;
- no tested perturbation changed strict primary-intent accuracy or
  acceptable-intent accuracy.

### Documentation

- Clarified that only 25 of 56 benchmark targets were retrieved among the
  top 300 Open Targets melanoma associations.
- Clarified that 100% stable-role accuracy measures consistency with the
  implemented curated rules rather than independent biological validation.
- Documented the scope and limitations of the internal benchmark and local
  weight-sensitivity analysis.

## [0.1.0] - 2026-07-09

### Added

- Open Targets melanoma-associated target retrieval with local caching.
- Stable biological and translational role classification.
- Resistance-axis ontology for anti-PD-1-resistant melanoma.
- Modality-aware reasoning for antibody, biomarker, and small-molecule use.
- Evidence auditing, contradiction detection, and confidence assignment.
- Therapeutic-intent-specific scoring profiles.
- Deterministic ranking and rank-shift analysis.
- Explainable hypothesis cards and HTML target reports.
- Benchmark and ranking visualizations.
- Curated 56-target therapeutic-intent benchmark.
- Augmented benchmark universe separating Open Targets retrieval coverage from
  TargetIntel-IO evaluation coverage.
- Versioned benchmark result snapshot with SHA-256 manifest.
- Automated benchmark snapshot regeneration command.
- Offline unit and regression test suite with 42 tests.
- GitHub Actions continuous integration.

### Benchmark snapshot

- TargetIntel evaluation coverage: 56/56 targets.
- Open Targets top-300 retrieval coverage: 25/56 targets.
- Stable-role accuracy: 100%.
- Strict primary-intent accuracy: 91.1%.
- Acceptable-intent accuracy: 100%.
- Cross-intent specificity: 90.6%.
- Mean top-10 recall: 58.1%.
- Mean top-20 recall: 79.5%.

### Fixed

- Corrected the Open Targets GraphQL disease argument to use `efoId` while
  retaining the valid melanoma identifier `MONDO_0005105`.
- Improved Open Targets HTTP and GraphQL error reporting.
- Prevented benchmark-only targets from receiving artificial Open Targets
  ranks.
- Corrected benchmark command formatting in the main README.

### Validation scope

The benchmark is an internal, rule-based sanity validation. It does not
constitute independent clinical validation, biomarker qualification, or
evidence of therapeutic efficacy.

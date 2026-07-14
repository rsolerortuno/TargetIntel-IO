# TargetIntel-IO

[![Tests](https://github.com/rsolerortuno/TargetIntel-IO/actions/workflows/tests.yml/badge.svg)](https://github.com/rsolerortuno/TargetIntel-IO/actions/workflows/tests.yml)
[![Latest release](https://img.shields.io/github/v/release/rsolerortuno/TargetIntel-IO)](https://github.com/rsolerortuno/TargetIntel-IO/releases/latest)
[![Python](https://img.shields.io/badge/Python-3.11-3776AB.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

**Explainable, therapeutic-intent-aware target intelligence for anti-PD-1-resistant melanoma.**

TargetIntel-IO is a reproducible scientific software project for classifying,
prioritizing, and explaining candidate therapeutic targets and biomarkers. It
combines a deterministic translational-biology baseline with an emerging,
auditable evidence layer designed for literature, functional genomics,
single-cell, spatial, and clinical-response data.

The project is built around one central question:

> **Not simply “What is the best target?” but “Best candidate for which
> therapeutic intent, supported by which evidence, and with which
> limitations?”**

---

## Project status

TargetIntel-IO currently has two complementary layers:

| Layer | Status | Purpose |
|---|---|---|
| **v0.1.3 deterministic baseline** | Available | Transparent target classification, therapeutic-intent ranking, benchmark evaluation, hypothesis cards, reports, and sensitivity analysis |
| **v0.2.0 evidence-layer development** | Partially implemented on `main` | Typed evidence contracts, semantic validation, immutable provenance, DuckDB storage, revision history, retrieval auditing, and future literature/LLM integration |

The production LLM extractor and literature copilot are **not yet implemented**.
The current v0.2.0 work establishes the traceable data and validation substrate
required to introduce them safely.

### Implemented in the v0.2.0 development line

- immutable `EvidenceItem`, `ProvenanceStep`, and `RetrievalAttempt` contracts;
- controlled scientific vocabularies and deterministic serialization;
- canonical JSON and SHA-256 content hashing;
- intrinsic, semantic, and cross-field validation;
- quoted-span requirements for literature-derived evidence;
- auditable support requirements for computed evidence;
- citation-verification and manual-curation provenance guards;
- derived-evidence lineage and cycle validation;
- explicit evidence-family eligibility fields;
- immutable DuckDB evidence storage;
- append-only provenance, audit events, and revision links;
- exact-duplicate detection and hash-collision protection;
- independent recording of retrieval success, zero results, failure,
  non-execution, and absent retrieval state;
- deterministic Parquet snapshot export and verification.

### Next milestones

- deterministic Europe PMC query construction and retrieval;
- mock extraction from frozen documents;
- literal quotation and citation verification;
- evidence-family construction and true-duplicate assessment;
- evidence cards integrated into the existing reports;
- provider-agnostic LLM extraction and target-level grounded synthesis;
- DepMap/CRISPR, single-cell, spatial, and clinical-cohort evidence adapters.

See the full [TargetIntel-IO 2.0 roadmap](docs/ROADMAP_2_0.md) and the detailed
[v0.2.0 evidence-layer specification](docs/specs/v0.2.0_evidence_layer.md).

---

## Why this project exists

A biologically relevant gene is not automatically a good drug target. Depending
on the evidence and therapeutic question, the same gene may instead be:

- a direct therapeutic target;
- an anti-PD-1 combination target;
- a resistance biomarker;
- a mechanistic resistance marker;
- a tumor-intrinsic driver;
- an immune-context signal;
- or a poor direct therapeutic candidate.

TargetIntel-IO makes these distinctions explicit. It preserves the reasoning
behind each classification and ranking rather than returning a single opaque
score.

---

## Architecture

```mermaid
flowchart TD
    OT[Open Targets] --> FT[Deterministic feature table]
    CFG[Curated resistance and modality rules] --> FT
    FT --> RC[Stable biological-role classifier]
    RC --> R1[Antibody / IO ranking]
    RC --> R2[Resistance-biomarker ranking]
    RC --> R3[Small-molecule ranking]
    R1 --> REP[Cards, HTML reports, figures]
    R2 --> REP
    R3 --> REP

    LIT[Scientific literature] -. v0.2 development .-> EI[Normalized EvidenceItems]
    DEP[DepMap / CRISPR] -. roadmap .-> EI
    SC[Single-cell / spatial] -. roadmap .-> EI
    CLIN[Clinical cohorts] -. roadmap .-> EI
    EI --> VAL[Deterministic validation]
    VAL --> DB[(Immutable DuckDB store)]
    DB --> EVR[Evidence-aware reports]
    DB -. future .-> LLM[Grounded LLM reasoner and critic]
    LLM --> EVR

    REP --> EVR
```

### Design principle: evidence before interpretation

The LLM is not intended to be the source of truth. Future model-generated
interpretations must be derived only from stored, source-linked evidence.
TargetIntel-IO therefore separates:

1. **retrieved or computed observations**;
2. **system-generated interpretations**;
3. **target-level recommendations**.

A recommendation must remain traceable to the exact observations, quotations,
datasets, cohorts, experiments, and transformations that support it.

---

## What the current workflow produces

For every candidate, the deterministic workflow generates:

- a stable biological and translational role;
- a therapeutic direction;
- matched anti-PD-1 resistance programs;
- modality-fit assessments;
- evidence supporting and arguing against prioritization;
- confidence and uncertainty annotations;
- separate rankings for three therapeutic intents;
- structured Markdown hypothesis cards;
- browsable HTML reports;
- summary figures and rank-shift analyses.

The three current ranking modes are:

| Mode | Prioritizes |
|---|---|
| **Antibody / IO combination** | Surface-accessible checkpoints, myeloid targets, suppressive immune axes, and combination rationale |
| **Resistance biomarker** | Antigen-presentation loss, IFNγ resistance, immune exclusion, and patient-stratification potential |
| **Small molecule** | Tumor-intrinsic drivers, kinases, oncogenic pathways, and small-molecule tractability |

---

## Evidence-layer example

A future literature or computational adapter will emit records using the same
core contract:

```python
EvidenceItem(
    evidence_id="ev_b2m_example",
    target_symbol="B2M",
    disease_name="melanoma",
    disease_id="MONDO:0005105",
    treatment_name="anti-PD-1",
    evidence_type="clinical_cohort",
    evidence_direction="supports_biomarker",
    observation="Source-grounded observation stored separately from interpretation.",
    interpretation=None,
    source="Europe PMC",
    source_id="PMID:...",
    quoted_span="Exact supporting source text.",
    patient_cohort_id="cohort_identifier",
    species="human",
    model_system="patient_tumor_biopsy",
    extraction_method="llm",
    validation_status="citation_verified",
    # additional provenance, family, timestamp, and integrity fields omitted
)
```

The evidence layer is designed to reject records that claim verification
without the required quotation, support, provenance, identifiers, and
validation history.

---

## Human-supervised multi-LLM development

Recent v0.2.0 development uses a **human-supervised multi-agent software
workflow**, while keeping scientific decisions and merges under human control.

```mermaid
flowchart LR
    H[Human scientific objective] --> S[Gemini-assisted specification]
    S --> I[Codex-assisted implementation]
    I --> T[Automated tests and regression gates]
    T --> R[Independent Claude review]
    R --> A[Adversarial audit]
    A --> H2[Human approval and merge]
```

The repository includes shared agent instructions that define non-negotiable
scientific and engineering constraints:

- never invent biological evidence, numerical values, references, or API data;
- never present association as proof of causality;
- never describe the internal benchmark as independent biological validation;
- preserve observation separately from LLM interpretation;
- prevent future LLM components from silently changing baseline rankings;
- protect secrets and identifiable patient-level information;
- require tests and explicit reporting of unresolved failures;
- require human approval before publishing changes.

See [`AGENTS.md`](AGENTS.md) and [`CLAUDE.md`](CLAUDE.md).

> Agentic AI is currently used to help engineer and review the platform. A
> production scientific LLM agent is part of the roadmap, not a completed
> feature.

---

## Quick start

### Conda

```bash
git clone https://github.com/rsolerortuno/TargetIntel-IO.git
cd TargetIntel-IO

conda env create -f environment.yml
conda activate targetintel
```

### Pip

```bash
git clone https://github.com/rsolerortuno/TargetIntel-IO.git
cd TargetIntel-IO

python -m venv .venv
source .venv/bin/activate

python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

---

## Run the deterministic workflow

Generate the feature table, therapeutic-intent rankings, target cards, HTML
reports, and figures:

```bash
targetintel run
```

Run the workflow with the internal benchmark and weight-sensitivity analysis:

```bash
targetintel run --validate
```

Force a new Open Targets request rather than using the local cache:

```bash
targetintel run --refresh
```

See all options:

```bash
targetintel run --help
```

---

## Main outputs

```text
data/processed/
└── targetintel_feature_table_v0_1.csv

results/
├── ranked_targets.csv
├── target_cards/
├── html_reports/
│   └── index.html
├── figures/
├── benchmark/
└── sensitivity/
```

After a successful run, open:

```text
results/html_reports/index.html
```

Versioned examples are available under:

- [`examples/html_reports/`](examples/html_reports/)
- [`examples/figures/`](examples/figures/)
- [`examples/benchmark/`](examples/benchmark/README.md)
- [`examples/sensitivity/`](examples/sensitivity/README.md)

---

## How the deterministic baseline works

### 1. Public evidence retrieval

The workflow retrieves melanoma-associated targets from the Open Targets
GraphQL API and caches the response locally for reproducibility.

### 2. Translational feature construction

Each target is annotated using:

- disease-association evidence;
- anti-PD-1 resistance-axis membership;
- therapeutic modality fit;
- tractability and known-drug evidence;
- safety and contradiction flags;
- evidence completeness and confidence.

### 3. Stable role classification

Each candidate receives one stable role independent of ranking mode. This
explicitly separates:

```text
therapeutic target ≠ biomarker ≠ resistance mechanism ≠ contextual marker
```

### 4. Therapeutic-intent-aware scoring

The same candidate is scored differently for antibody/IO, biomarker, and
small-molecule use. Every final score retains its component values, penalties,
role interpretation, and supporting or opposing evidence.

### 5. Human-readable outputs

The workflow converts the ranked table into hypothesis cards, HTML reports,
figures, benchmark summaries, and machine-readable validation outputs.

---

## Internal benchmark snapshot

TargetIntel-IO includes a curated 56-target benchmark for internal rule-based
sanity validation.

| Metric | Result |
|---|---:|
| Benchmark targets evaluated | 56 / 56 |
| TargetIntel evaluation coverage | 100% |
| Open Targets top-300 retrieval coverage | 44.6% |
| Stable-role accuracy | 100.0% |
| Strict primary-intent accuracy | 91.1% |
| Acceptable-intent accuracy | 100.0% |
| Cross-intent specificity | 90.6% |
| Control not-prioritized rate | 100.0% |
| Mean top-10 recall | 58.1% |
| Mean top-20 recall | 79.5% |

Only **25/56 benchmark targets (44.6%)** appeared among the top 300 melanoma
associations retrieved from Open Targets. The remaining targets were added to
the augmented benchmark universe without claiming that Open Targets recovered
them.

The benchmark's expected roles were curated using the same translational
framework represented by the implemented rules. The results therefore measure
implementation consistency and internal sanity, **not independent biological,
clinical, or prospective accuracy**.

Complete results and per-target predictions are available in the
[versioned benchmark snapshot](examples/benchmark/README.md).

---

## Weight sensitivity

The local sensitivity analysis evaluates **42 scenarios** in which one scoring
weight is changed by `-20%` or `+20%` and all weights are subsequently
renormalized.

- Worst-case top-5 retention:
  **antibody/IO 100%, biomarker 100%, small-molecule 80%**.
- Worst-case top-10 retention:
  **antibody/IO 90%, biomarker 100%, small-molecule 90%**.
- Worst-case top-20 retention:
  **antibody/IO 100%, biomarker 95%, small-molecule 100%**.
- Minimum observed Spearman rank correlation: **0.8762**.
- Maximum absolute change in strict primary-intent accuracy:
  **5.36 percentage points**.

![Worst-case ranking stability](examples/sensitivity/sensitivity_overview.png)

This analysis shows local stability around the selected scoring configuration.
It does not establish that the rankings are independent of weight selection or
that the weights are biologically optimal.

---

## Reproducibility and software quality

The project includes:

- a reusable Python package and command-line interface;
- compatible dependency ranges in `pyproject.toml`;
- a Conda environment definition;
- an exact Python 3.11 lockfile with package hashes;
- local API caching;
- deterministic ranking and tie-breaking;
- versioned benchmark and sensitivity snapshots;
- SHA-256 snapshot manifests;
- GitHub Actions continuous integration;
- offline unit and regression tests;
- immutable evidence storage and Parquet snapshot verification;
- explicit scientific and AI-agent safety instructions.

Install the exact locked environment used by CI:

```bash
python -m pip install \
  --require-hashes \
  --requirement requirements-lock.txt

python -m pip install \
  --no-deps \
  --no-build-isolation \
  --editable .
```

Run the test suite:

```bash
python -m pytest tests -q
```

---

## Repository map

```text
configs/            Disease context, resistance axes, benchmark, and scoring YAMLs
targetintel/        Reusable Python package and command-line workflow
targetintel/evidence/
                    Typed evidence contracts, validation, and immutable storage
scripts/            Individual pipeline and snapshot-management commands
tests/              Unit, integration, and regression tests
examples/           Versioned reports, figures, benchmark, and sensitivity outputs
docs/               Architecture, roadmap, and evidence-layer specifications
data/               Local cached and processed data, excluded from version control
results/            Generated local outputs, excluded from version control
```

---

## Scope and limitations

TargetIntel-IO is a hypothesis-generation and target-triage framework. It does
not provide:

- clinical recommendations;
- validated therapeutic targets;
- qualified biomarkers;
- causal biological proof;
- a clinically validated diagnostic system;
- patient-level treatment predictions;
- or medical advice.

The current deterministic implementation is specific to anti-PD-1-resistant
melanoma. Association evidence does not establish causality, tractability,
safety, clinical benefit, or successful combination therapy.

The v0.2.0 evidence layer currently provides infrastructure rather than a
completed literature copilot. Real LLM-generated scientific interpretations,
production literature extraction, DepMap integration, single-cell/spatial
analysis, patient-response modelling, and knowledge-graph inference remain
future work.

All generated hypotheses require independent experimental, translational, and
clinical validation.

---

## Data sources and data governance

The current deterministic workflow uses public data and curated public-domain
biological knowledge. Its principal external source is the Open Targets
Platform GraphQL API.

No confidential, proprietary, company-internal, or identifiable patient data
is included in the repository. Local caches, generated evidence databases, and
analysis outputs are excluded from version control by default.

---

## Citation

```text
Soler Ortuño R. TargetIntel-IO: Explainable therapeutic-intent-aware target
intelligence for anti-PD-1-resistant melanoma.
```

---

## Author

**Rafael Soler Ortuño, PhD**

Computational biologist working at the intersection of immuno-oncology,
biomarker discovery, patient stratification, multi-omics, single-cell and
spatial transcriptomics, scientific software engineering, and AI-assisted drug
discovery.

[LinkedIn](https://www.linkedin.com/in/rafael-soler-ortuno/)

---

## License

Released under the [MIT License](LICENSE).

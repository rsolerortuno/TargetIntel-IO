# TargetIntel

**AI-assisted immuno-oncology target discovery using public multi-omics evidence, Open Targets, DepMap, single-cell/spatial transcriptomics, and LLM-generated evidence reports.**

---

## Overview

**TargetIntel** is a portfolio project that demonstrates how public biological data, functional genomics, single-cell/spatial analysis, and AI-assisted evidence synthesis can be combined to prioritize therapeutic targets for immuno-oncology.

The first MVP focuses on:

> **Prioritizing candidate targets for anti-PD-1-resistant melanoma using public evidence sources.**

The goal is not to claim a new validated drug target, but to build a reproducible and interpretable computational framework for target prioritization, biomarker exploration, and patient-stratification hypothesis generation.

---

## Project goals

TargetIntel aims to answer questions such as:

* Which genes are promising therapeutic targets in a specific immuno-oncology context?
* What public evidence supports or weakens each target?
* Is the target expressed in disease-relevant immune, tumor, or stromal cell states?
* Is there functional-genomics evidence from CRISPR or cancer-dependency screens?
* Is the target associated with patient survival, treatment response, or disease biology?
* Can an LLM summarize the evidence in a clear, cited, and biologically interpretable report?

---

## MVP use case

The first case study is:

**Anti-PD-1-resistant melanoma**

The MVP will generate a ranked list of candidate targets using public evidence from:

* Open Targets
* DepMap / CRISPR dependency data
* TCGA or public melanoma cohorts
* Public single-cell RNA-seq datasets
* Public spatial transcriptomics datasets, when available
* Literature-derived evidence
* Optional LLM-based evidence summarization

---

## Planned evidence layers

Each target will be scored using multiple evidence types:

| Evidence layer                       | Purpose                                                  |
| ------------------------------------ | -------------------------------------------------------- |
| Open Targets evidence                | Disease association, tractability, safety, known drugs   |
| DepMap / CRISPR evidence             | Functional dependency and cancer vulnerability           |
| Bulk transcriptomics / clinical data | Expression, survival, patient-response associations      |
| Single-cell transcriptomics          | Cell-type and cell-state-specific expression             |
| Spatial transcriptomics              | Tissue niche and tumor microenvironment localization     |
| Literature / clinical trials         | Biological rationale, clinical precedent, contradictions |
| LLM-generated report                 | Human-readable synthesis of evidence for each target     |

---

## Initial target scoring framework

The first version uses an interpretable weighted score:

```text
Final target score =
  40% Open Targets / disease evidence
+ 25% DepMap / CRISPR evidence
+ 20% expression / cell-state evidence
+ 15% tractability / safety evidence
```

This scoring system will be refined as more data layers are added.

---

## Repository structure

```text
targetintel/
├── README.md
├── notebooks/
│   └── 01_target_prioritization_mvp.ipynb
├── src/
│   ├── opentargets.py
│   ├── depmap.py
│   ├── scoring.py
│   └── utils.py
├── data/
│   ├── raw/
│   └── processed/
├── results/
├── figures/
├── app/
│   └── streamlit_app.py
├── requirements.txt
├── environment.yml
├── .gitignore
└── LICENSE
```

---

## Current status

This project is in early development.

### Version 0.1 goals

* [ ] Create reproducible project structure
* [ ] Query Open Targets for melanoma-associated targets
* [ ] Build first target-prioritization table
* [ ] Add a simple target scoring function
* [ ] Export ranked targets to `results/`
* [ ] Generate first summary figure
* [ ] Document assumptions and limitations

### Version 0.2 goals

* [ ] Add DepMap / CRISPR dependency evidence
* [ ] Add TCGA or public melanoma expression data
* [ ] Add single-cell expression validation
* [ ] Generate top 10 target evidence table

### Version 0.3 goals

* [ ] Build a simple Streamlit app
* [ ] Add LLM-generated target reports using cached results
* [ ] Create a visual project page or blog post

---

## Example output

The final MVP will produce a table similar to:

| Rank | Target   | Final score | Main supporting evidence                                     | Main concern               |
| ---: | -------- | ----------: | ------------------------------------------------------------ | -------------------------- |
|    1 | TARGET_A |          87 | Disease association, immune-cell expression, CRISPR evidence | Broad normal expression    |
|    2 | TARGET_B |          82 | TME-specific expression, survival association                | Limited clinical precedent |
|    3 | TARGET_C |          78 | Functional dependency, pathway relevance                     | Weak spatial evidence      |

Each target will also have a short evidence report including:

* Biological rationale
* Evidence supporting the target
* Evidence against the target
* Relevant cell types or tumor microenvironment niches
* Functional-genomics support
* Suggested validation experiment
* Confidence score

---

## Installation

Clone the repository:

```bash
git clone https://github.com/YOUR_USERNAME/targetintel.git
cd targetintel
```

Create the environment:

```bash
conda env create -f environment.yml
conda activate targetintel
```

Or install with pip:

```bash
pip install -r requirements.txt
```

---

## Usage

The first MVP notebook is:

```text
notebooks/01_target_prioritization_mvp.ipynb
```

Run this notebook to:

1. Query or load public target-disease evidence
2. Create a candidate target table
3. Calculate preliminary target scores
4. Export ranked results
5. Generate initial figures

Future versions will include command-line and Streamlit interfaces.

---

## Planned Streamlit demo

The Streamlit app will allow users to:

* Select a disease context
* Explore ranked targets
* Inspect evidence layers
* View target-specific plots
* Generate an LLM-assisted evidence report
* Download ranked target tables

The public demo will use precomputed results to avoid unnecessary cloud or GPU costs.

---

## Data policy

This project uses **public data only**.

No confidential, proprietary, clinical, or company-internal data is included.

The project is designed as an open portfolio framework inspired by translational immuno-oncology workflows, but all analyses are based on public resources.

---

## Limitations

TargetIntel is a research and portfolio tool.

It does **not** provide clinical recommendations, validated therapeutic targets, or medical advice.

Target scores are hypothesis-generating and depend on:

* Public data availability
* Dataset quality
* Scoring assumptions
* Disease-context definition
* Model and preprocessing choices

All findings require experimental and clinical validation.

---

## Roadmap

Planned future additions:

* DepMap and PRISM integration
* Single-cell melanoma immune atlas validation
* Spatial transcriptomics evidence layer
* Survival and treatment-response modeling
* LLM/RAG-based evidence reports
* BioNeMo or protein-embedding demonstration
* Docker container
* GitHub Pages / Quarto project website
* Streamlit interactive dashboard

---

## Tech stack

Planned tools and libraries include:

* Python
* pandas
* numpy
* scanpy
* scikit-learn
* matplotlib
* seaborn
* requests
* Open Targets GraphQL API
* DepMap public datasets
* Streamlit
* LangChain or LlamaIndex
* Docker
* GitHub Actions

---

## Author

**Rafael Soler Ortuño**
Computational Biologist focused on immuno-oncology, biomarker discovery, patient stratification, single-cell/spatial transcriptomics, and AI-assisted drug discovery.

LinkedIn: https://www.linkedin.com/in/rafael-soler-ortuno/

---

## License

This project is released under the MIT License.

---

## Citation

A citation file will be added in a future release.

```text
TargetIntel: AI-assisted immuno-oncology target discovery using public multi-omics evidence.
```

# DepMap Public 26Q1 source and publication guide

TargetIntel-IO v0.5.0 uses the validated `DepMap_Public_26Q1` closure for an
optional, post-ranking functional-dependency research preview. Obtain bulk
data only from the official [DepMap downloads page](https://depmap.org/portal/data_page/?release=DepMap+Public+26Q1), not by scraping interactive portal pages. The official [26Q1 release notes](https://forum.depmap.org/t/announcing-the-26q1-release/4606) provide release context.

The published [`source_manifest.json`](../../data/releases/depmap/DepMap_Public_26Q1/source_manifest.json)
records the exact filenames, SHA-256 checksums, sizes, and roles from the
validated download ledger. The validated run used `CRISPRGeneEffect.csv` for
gene-effect aggregates, `CRISPRGeneDependency.csv` for dependency-probability
aggregates, and `Model.csv` for model-context metadata; its ledger also records
`Gene.csv`, `CRISPRInferredCommonEssentials.csv`, and `README.txt`. Raw inputs
are not redistributed.

Place official downloads beneath a directory such as
`<DEPMAP_RELEASE_ROOT>`. Run the validated closure externally, then publish
only its already-derived aggregate output:

```bash
python scripts/13_publish_depmap_v050.py \
  --run-dir <VALIDATED_RUN_ROOT> \
  --config-dir <VALIDATED_RUN_ROOT>/config \
  --manifest-dir <DEPMAP_RELEASE_ROOT>/manifests \
  --ranked-targets <VALIDATED_RUN_ROOT>/ranked_targets.tsv \
  --output-dir <PUBLICATION_OUTPUT_ROOT>/data/releases/depmap/DepMap_Public_26Q1 \
  --html-output-dir <PUBLICATION_OUTPUT_ROOT>/examples/html_reports/depmap_26q1 \
  --cards-output-dir <PUBLICATION_OUTPUT_ROOT>/examples/target_cards/depmap_26q1
```

The command performs no network access, DepMap ingestion, profile calculation,
benchmark calculation, integration calculation, or raw-matrix modification.
It validates identities, creates aggregate records for all 331 discovery
identities, and rejects unsafe paths and oversized output. After successful
publication, the normal report workflow can use the bundle without the
original matrices:

```bash
targetintel run --depmap-snapshot data/releases/depmap/DepMap_Public_26Q1
```

Raw matrices, complete model metadata, screen-level matrices, full
18,531-gene profile JSONL, archives, caches, and operational logs remain
excluded. The bundle contains only portable aggregate report evidence.

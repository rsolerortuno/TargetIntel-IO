# Fabricated offline evidence demo

This deterministic demonstration exercises fixture extraction, validation,
literal quotation verification, evidence-family assignment, hashing, DuckDB
storage, read-only loading, and Markdown/HTML report decoration. Every source,
identifier, context, and observation is fabricated mock data; it makes no
scientific or clinical claim.

Run without network access:

```bash
python examples/evidence/build_mock_evidence_demo.py --output-dir /tmp/targetintel-evidence-demo
```

The selected directory contains a DuckDB store, a Markdown evidence card, and
an HTML evidence report. Do not commit generated stores or output directories.

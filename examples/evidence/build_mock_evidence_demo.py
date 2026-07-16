"""Build a deterministic, fabricated evidence-layer demonstration offline."""

from __future__ import annotations

import argparse
from pathlib import Path
import tempfile

from targetintel.evidence.extractor import MockExtractor, SourceDocument
from targetintel.evidence.pipeline_integration import load_evidence_cards
from targetintel.evidence.store import EvidenceStore
from targetintel.evidence.verifier import EvidenceFinalizer


DOCUMENT = {
    "fixture_id": "release-demo-v1",
    "source": "Fabricated offline document",
    "source_id": "fabricated-doc-001",
    "target_symbol": "MOCK_DEMO",
    "target_id": "MOCK:DEMO",
    "disease_name": "fabricated context",
    "disease_id": "MONDO:MOCK",
    "treatment_name": "fabricated treatment",
    "treatment_id": "MOCK:TX",
    "document_location": "fabricated-results",
    "source_text": "Fabricated document. MOCK_DEMO observation is a mock record.",
    "structured_content": None,
    "publication_id": "FABRICATED:001",
    "source_dataset_id": None,
    "patient_cohort_id": "fabricated-cohort",
    "experiment_id": None,
    "retrieved_at": "2026-07-16T00:00:00Z",
    "data_release": "fabricated-v1",
    "candidates": [{
        "fixture_candidate_id": "001",
        "evidence_type": "clinical_cohort",
        "evidence_direction": "neutral",
        "observation": "MOCK_DEMO observation is a mock record.",
        "quoted_span": "MOCK_DEMO observation is a mock record.",
        "computed_support": None,
        "species": "human",
        "model_system": "patient_tumor_biopsy",
        "sample_context": "fabricated samples",
        "effect_size": None,
        "effect_size_metric": None,
        "uncertainty": None,
        "uncertainty_metric": None,
        "sample_size": None,
        "extraction_confidence": 1.0,
    }],
}


def build_demo(output_dir: Path) -> tuple[Path, Path, Path]:
    """Create one fabricated store and its Markdown and HTML evidence cards."""
    output_dir.mkdir(parents=True, exist_ok=True)
    document = SourceDocument.from_dict(DOCUMENT)
    candidate = MockExtractor().extract(document)[0]
    finalized = EvidenceFinalizer().finalize(candidate, document).item
    store_path = output_dir / "mock_evidence.duckdb"
    with EvidenceStore(store_path) as store:
        store.insert_finalized_item(finalized)
    card = load_evidence_cards(store_path, [document.target_symbol])[document.target_symbol]
    item = card.items[0]
    markdown = output_dir / "mock_evidence_card.md"
    markdown.write_text(
        "# Fabricated evidence card\n\n"
        "This offline demonstration contains fabricated mock data only.\n\n"
        f"- Target: `{card.target_symbol}`\n"
        f"- Observation: {item.observation}\n"
        f"- Source: {item.source} ({item.source_id})\n"
        f"- Quotation: {item.quoted_span}\n"
        f"- Validation: {item.validation_status}\n",
        encoding="utf-8",
    )
    html = output_dir / "mock_evidence_report.html"
    html.write_text(
        "<!doctype html><html><body><h1>Fabricated evidence report</h1>"
        "<p>This offline demonstration contains fabricated mock data only.</p>"
        f"<p>Target: {card.target_symbol}</p><p>Observation: {item.observation}</p>"
        f"<p>Validation: {item.validation_status}</p></body></html>\n",
        encoding="utf-8",
    )
    return store_path, markdown, html


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, help="Directory for the fabricated demo outputs.")
    args = parser.parse_args(argv)
    if args.output_dir is None:
        with tempfile.TemporaryDirectory(prefix="targetintel-evidence-demo-") as temporary:
            paths = build_demo(Path(temporary))
            print("Built fabricated offline evidence demo in a temporary directory:", *paths, sep="\n")
    else:
        paths = build_demo(args.output_dir)
        print("Built fabricated offline evidence demo:", *paths, sep="\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

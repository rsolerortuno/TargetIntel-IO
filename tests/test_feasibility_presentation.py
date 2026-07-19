"""Offline tests for post-ranking feasibility decoration."""

import hashlib
from dataclasses import FrozenInstanceError, replace

import pandas as pd
import pytest

from targetintel.feasibility import FeasibilityObservation, TargetFeasibilityProfile, TargetFeasibilityRequest
from targetintel.feasibility.models import OBSERVATION_FORMAT_VERSION, REQUEST_SCHEMA_ID, REQUEST_SCHEMA_VERSION
from targetintel.feasibility.presentation import FeasibilityPresentationError, make_feasibility_report_section, render_feasibility_markdown
from targetintel.hypothesis_cards import make_target_card, write_top_target_cards
from targetintel.html_reports import make_target_html_report, write_top_html_reports
from targetintel.modality import assign_modality_fit, compose_modality_with_feasibility


def _annotation(modality="antibody", observations=()):
    request = TargetFeasibilityRequest(REQUEST_SCHEMA_ID, REQUEST_SCHEMA_VERSION, "BRAF", "gene_symbol", "melanoma",
        ("clinical_precedence", "tractability", "doability", "safety"), ("antibody", "small_molecule", "protac", "other_clinical"), "Open Targets", "24.06", "test")
    profile = TargetFeasibilityProfile.from_request(request, observations)
    return compose_modality_with_feasibility(assign_modality_fit("BRAF"), profile, modality,
        target_identifier="BRAF", target_identifier_type="gene_symbol").feasibility_annotation


def _observation(dimension, modality, factor="factor", value=True, state="observed", value_type="boolean"):
    return FeasibilityObservation(OBSERVATION_FORMAT_VERSION, "BRAF", "gene_symbol", dimension, modality,
        factor, value, value_type, state, "Open Targets", "24.06", "record", dimension,
        {"release_verification_state": "verified"}, ("source-limited",))


def _row():
    return pd.Series({"target_symbol": "BRAF", "target_name": "B-Raf", "antibody_io_rank": 2, "biomarker_rank": 3, "small_molecule_rank": 1})


def test_legacy_cards_and_html_are_exactly_unchanged_without_feasibility():
    row = _row()
    card = make_target_card(row)
    html = make_target_html_report(row)

    # These SHA-256 values are fixed from the pre-Issue-405 canonical renderers
    # for _row().  They anchor the complete legacy byte stream, including
    # trailing whitespace, rather than comparing two calls to this implementation.
    assert hashlib.sha256(card.encode("utf-8")).hexdigest() == (
        "e26f1c498bc92affa5e279bc21db97eda66012622858d83ed88e3baefb15aac0"
    )
    assert hashlib.sha256(html.encode("utf-8")).hexdigest() == (
        "f7c13d48a82bb711c9384824eb367d8b97f6221f72143568395166653fef5f6a"
    )
    assert card == make_target_card(row, feasibility_annotations=None)
    assert html == make_target_html_report(row, feasibility_annotations=None)


def test_section_is_immutable_and_deterministic_across_caller_ordering():
    antibody = _annotation("antibody", (_observation("tractability", "antibody"),))
    small = _annotation("small_molecule", (_observation("tractability", "small_molecule"),))
    first = make_feasibility_report_section(target_identifier="BRAF", target_identifier_type="gene_symbol", annotations=(small, antibody))
    second = make_feasibility_report_section(target_identifier="BRAF", target_identifier_type="gene_symbol", annotations=(antibody, small))
    assert first.section_id == second.section_id
    assert first.to_dict() == second.to_dict()
    assert [item["requested_modality"] for item in first.to_dict()["modalities"]] == ["antibody", "small_molecule"]
    with pytest.raises(FrozenInstanceError): first.target_identifier = "NRAS"


def test_markdown_retains_context_missingness_contradictions_and_safety_restraint():
    positive = _observation("tractability", "antibody", "same", True)
    negative = _observation("tractability", "antibody", "same", False)
    safety = _observation("safety", None, "none", None, "not_observed", "null")
    section = make_feasibility_report_section(target_identifier="BRAF", target_identifier_type="gene_symbol", annotations=(_annotation("antibody", (positive, negative, safety)),))
    text = render_feasibility_markdown(section)
    assert "Target feasibility — research-only" in text
    assert "Feasibility did not modify target scores" in text
    assert "Absence of a retrieved safety signal is not evidence that a target is safe." in text
    assert "Contradictions retained without resolution" in text
    assert positive.observation_id in text and negative.observation_id in text
    assert "Target-level contextual observation references" in text
    assert "The target is safe" not in text


def test_cards_and_html_add_only_a_post_ranking_section_and_escape_values():
    annotation = replace(_annotation("antibody", (_observation("tractability", "antibody"),)), source_name="<script>alert(1)</script>")
    row = _row()
    baseline_card, baseline_html = make_target_card(row), make_target_html_report(row)
    card = make_target_card(row, feasibility_annotations=(annotation,), feasibility_target_identifier_type="gene_symbol")
    html = make_target_html_report(row, feasibility_annotations=(annotation,), feasibility_target_identifier_type="gene_symbol")
    assert card.startswith(baseline_card.rstrip() + "\n")
    assert "## Target feasibility — research-only" in card
    assert "<h2>Therapeutic-intent rankings</h2>" in baseline_html
    assert "<h2>Therapeutic-intent rankings</h2>" in html
    assert "&amp;lt;script&amp;gt;" in html


def test_top_level_writers_preserve_selection_order_and_route_annotations(tmp_path):
    """Decoration is applied only after canonical selection and ordering."""
    ranked_df = pd.DataFrame([
        {**_row().to_dict(), "target_symbol": "BRAF", "antibody_io_rank": 1,
         "biomarker_rank": 3, "small_molecule_rank": 3},
        {**_row().to_dict(), "target_symbol": "NRAS", "antibody_io_rank": 3,
         "biomarker_rank": 1, "small_molecule_rank": 3},
        {**_row().to_dict(), "target_symbol": "TP53", "antibody_io_rank": 3,
         "biomarker_rank": 3, "small_molecule_rank": 1},
    ])
    annotations = {"BRAF": (_annotation("antibody", (_observation("tractability", "antibody"),)),)}

    baseline_cards = write_top_target_cards(
        ranked_df, output_dir=tmp_path / "baseline_cards", top_n_per_mode=1,
    )
    decorated_cards = write_top_target_cards(
        ranked_df, output_dir=tmp_path / "decorated_cards", top_n_per_mode=1,
        feasibility_annotations=annotations,
        feasibility_target_identifier_type="gene_symbol",
    )
    baseline_html = write_top_html_reports(
        ranked_df, output_dir=tmp_path / "baseline_html", top_n_per_mode=1,
    )
    decorated_html = write_top_html_reports(
        ranked_df, output_dir=tmp_path / "decorated_html", top_n_per_mode=1,
        feasibility_annotations=annotations,
        feasibility_target_identifier_type="gene_symbol",
    )

    assert [path.name for path in decorated_cards] == [path.name for path in baseline_cards] == [
        "BRAF.md", "NRAS.md", "TP53.md",
    ]
    assert [path.name for path in decorated_html] == [path.name for path in baseline_html] == [
        "index.html", "BRAF.html", "NRAS.html", "TP53.html",
    ]

    for baseline, decorated in zip(baseline_cards, decorated_cards):
        if decorated.name == "BRAF.md":
            assert "Target feasibility — research-only" in decorated.read_text(encoding="utf-8")
        else:
            assert decorated.read_text(encoding="utf-8") == baseline.read_text(encoding="utf-8")
    for baseline, decorated in zip(baseline_html, decorated_html):
        if decorated.name == "BRAF.html":
            assert "Target feasibility — research-only" in decorated.read_text(encoding="utf-8")
        else:
            assert decorated.read_text(encoding="utf-8") == baseline.read_text(encoding="utf-8")


@pytest.mark.parametrize("replacement, code", [
    ({"target_identifier": "NRAS"}, "target_mismatch"),
    ({"target_identifier_type": "ensembl_gene_id"}, "identifier_type_mismatch"),
    ({"annotation_format_version": "v0"}, "unsupported_annotation_version"),
])
def test_invalid_annotation_identity_fails_closed(replacement, code):
    annotation = replace(_annotation(), **replacement)
    with pytest.raises(FeasibilityPresentationError, match=code):
        make_feasibility_report_section(target_identifier="BRAF", target_identifier_type="gene_symbol", annotations=(annotation,))


def test_duplicate_modality_and_observation_references_fail_closed():
    annotation = _annotation("antibody", (_observation("tractability", "antibody"),))
    with pytest.raises(FeasibilityPresentationError, match="duplicate_modality_annotation"):
        make_feasibility_report_section(target_identifier="BRAF", target_identifier_type="gene_symbol", annotations=(annotation, annotation))
    duplicate = replace(annotation, target_context_observation_ids=annotation.modality_specific_observation_ids)
    with pytest.raises(FeasibilityPresentationError, match="duplicate_observation_reference"):
        make_feasibility_report_section(target_identifier="BRAF", target_identifier_type="gene_symbol", annotations=(duplicate,))

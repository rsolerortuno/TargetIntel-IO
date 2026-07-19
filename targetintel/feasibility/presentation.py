"""Pure, post-ranking feasibility presentation contracts.

This module consumes only the immutable public modality-feasibility annotation
contract.  It neither retrieves nor rebuilds feasibility data, and has no
dependency on TargetIntel scoring, ranking, role, evidence, or LLM layers.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from html import escape as html_escape
from types import MappingProxyType
from typing import Any, Mapping, Sequence

from .models import THERAPEUTIC_MODALITIES, canonical_json
from .profiles import FeasibilityDimensionCoverage


SECTION_FORMAT_VERSION = "v0.4.0"
_DIMENSIONS = ("clinical_precedence", "tractability", "doability", "safety")
_MODALITIES = ("antibody", "small_molecule", "protac", "other_clinical")
_COVERAGE_STATES = frozenset({
    "observed", "partial", "not_available", "not_applicable", "conflicting",
    "retrieval_failed",
})


class FeasibilityPresentationError(ValueError):
    """Sanitized deterministic error for invalid presentation input."""


def _identity(payload: Mapping[str, Any]) -> str:
    return "frs_" + sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def _annotation(value: Any) -> Any:
    """Accept the Issue 404 annotation or its composition result only."""
    if type(value).__module__ != "targetintel.modality":
        raise FeasibilityPresentationError("invalid_feasibility_annotation")
    if type(value).__name__ == "ModalityAssessmentWithFeasibility":
        value = value.feasibility_annotation
    if type(value).__module__ != "targetintel.modality" or type(value).__name__ != "ModalityFeasibilityAnnotation":
        raise FeasibilityPresentationError("invalid_feasibility_annotation")
    return value


def _coverage_key(item: FeasibilityDimensionCoverage) -> tuple[int, int, str]:
    return (_DIMENSIONS.index(item.dimension), -1 if item.modality is None else _MODALITIES.index(item.modality), item.coverage_id)


def _validate_annotation(value: Any, target_identifier: str, target_identifier_type: str) -> Any:
    annotation = _annotation(value)
    if annotation.annotation_format_version != SECTION_FORMAT_VERSION:
        raise FeasibilityPresentationError("unsupported_annotation_version")
    if not annotation.annotation_id or not annotation.feasibility_profile_id:
        raise FeasibilityPresentationError("missing_annotation_identity")
    if annotation.target_identifier != target_identifier:
        raise FeasibilityPresentationError("target_mismatch")
    if annotation.target_identifier_type != target_identifier_type:
        raise FeasibilityPresentationError("identifier_type_mismatch")
    if annotation.requested_modality not in THERAPEUTIC_MODALITIES:
        raise FeasibilityPresentationError("unsupported_modality")
    if not (annotation.research_only and annotation.no_score_calculated and annotation.no_ranking_modified and annotation.no_recommendation_generated):
        raise FeasibilityPresentationError("invalid_feasibility_annotation")
    identifiers = []
    for field in ("modality_specific_observation_ids", "target_context_observation_ids"):
        reference_map = getattr(annotation, field)
        if not isinstance(reference_map, Mapping) or set(reference_map) != set(_DIMENSIONS):
            raise FeasibilityPresentationError("malformed_observation_references")
        for dimension in _DIMENSIONS:
            references = reference_map[dimension]
            if not isinstance(references, tuple) or any(not isinstance(item, str) or not item for item in references):
                raise FeasibilityPresentationError("malformed_observation_references")
            identifiers.extend(references)
    if len(identifiers) != len(set(identifiers)):
        raise FeasibilityPresentationError("duplicate_observation_reference")
    coverage_ids = []
    for coverage in annotation.dimension_coverage:
        if not isinstance(coverage, FeasibilityDimensionCoverage) or coverage.coverage_state not in _COVERAGE_STATES:
            raise FeasibilityPresentationError("malformed_coverage")
        if coverage.target_identifier != target_identifier or coverage.target_identifier_type != target_identifier_type:
            raise FeasibilityPresentationError("malformed_coverage")
        coverage_ids.append(coverage.coverage_id)
    if len(coverage_ids) != len(set(coverage_ids)):
        raise FeasibilityPresentationError("malformed_coverage")
    return annotation


def _references(annotation: Any, field: str) -> Mapping[str, tuple[str, ...]]:
    values = getattr(annotation, field)
    return MappingProxyType({dimension: tuple(values[dimension]) for dimension in _DIMENSIONS})


@dataclass(frozen=True)
class FeasibilityReportSection:
    """Immutable, descriptive feasibility decoration for one report target."""

    section_format_version: str
    target_identifier: str
    target_identifier_type: str
    annotations: tuple[Any, ...]
    research_only_statement: str = "Research-only feasibility context; it does not constitute a therapeutic recommendation."
    no_score_statement: str = "Feasibility did not modify target scores or score components."
    no_ranking_statement: str = "Feasibility did not modify roles, intent labels, ranks, ordering, selection, or benchmark membership."
    no_recommendation_statement: str = "No modality recommendation or go/no-go conclusion is generated."
    safety_data_limitation_statement: str = "Absence of a retrieved safety signal is not evidence that a target is safe."

    @property
    def section_id(self) -> str:
        return _identity(self.identity_payload())

    def identity_payload(self) -> dict[str, Any]:
        return {
            "section_format_version": self.section_format_version,
            "target_identifier": self.target_identifier,
            "target_identifier_type": self.target_identifier_type,
            "annotations": [annotation.annotation_id for annotation in self.annotations],
            "research_only_statement": self.research_only_statement,
            "no_score_statement": self.no_score_statement,
            "no_ranking_statement": self.no_ranking_statement,
            "no_recommendation_statement": self.no_recommendation_statement,
            "safety_data_limitation_statement": self.safety_data_limitation_statement,
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            **self.identity_payload(),
            "section_id": self.section_id,
            "modalities": [
                {
                    "requested_modality": annotation.requested_modality,
                    "annotation_id": annotation.annotation_id,
                    "feasibility_profile_id": annotation.feasibility_profile_id,
                    "source_name": annotation.source_name,
                    "source_release": annotation.source_release,
                    "release_verification_states": list(annotation.release_verification_states),
                    "modality_specific_observation_references": {key: list(value) for key, value in _references(annotation, "modality_specific_observation_ids").items()},
                    "target_context_observation_references": {key: list(value) for key, value in _references(annotation, "target_context_observation_ids").items()},
                    "coverage": [item.to_dict() for item in sorted(annotation.dimension_coverage, key=_coverage_key)],
                    "contradiction_observation_ids": list(annotation.contradiction_observation_ids),
                    "limitations": list(annotation.limitations),
                }
                for annotation in self.annotations
            ],
        }


def make_feasibility_report_section(
    *, target_identifier: str, target_identifier_type: str, annotations: Sequence[Any]
) -> FeasibilityReportSection:
    """Validate and canonically order already-constructed Issue 404 annotations."""
    if not isinstance(target_identifier, str) or not target_identifier:
        raise FeasibilityPresentationError("target_mismatch")
    if not isinstance(target_identifier_type, str) or not target_identifier_type:
        raise FeasibilityPresentationError("identifier_type_mismatch")
    if not isinstance(annotations, (tuple, list)) or not annotations:
        raise FeasibilityPresentationError("invalid_feasibility_annotation")
    validated = tuple(_validate_annotation(item, target_identifier, target_identifier_type) for item in annotations)
    modalities = [item.requested_modality for item in validated]
    if len(modalities) != len(set(modalities)):
        raise FeasibilityPresentationError("duplicate_modality_annotation")
    return FeasibilityReportSection(
        SECTION_FORMAT_VERSION, target_identifier, target_identifier_type,
        tuple(sorted(validated, key=lambda item: (_MODALITIES.index(item.requested_modality), item.annotation_id))),
    )


def _markdown(value: Any) -> str:
    return str(value).replace("\\", "\\\\").replace("`", "\\`").replace("<", "&lt;").replace(">", "&gt;").replace("\n", " ")


def _coverage_text(coverage: FeasibilityDimensionCoverage) -> str:
    modality = "target-level context" if coverage.modality is None else coverage.modality
    return f"{coverage.dimension} ({modality}): {coverage.coverage_state}"


def render_feasibility_markdown(section: FeasibilityReportSection) -> str:
    """Render deterministic research-only Markdown; no source payload is copied."""
    lines = ["## Target feasibility — research-only", "", f"- {section.research_only_statement}", f"- {section.no_score_statement}", f"- {section.no_ranking_statement}", f"- {section.no_recommendation_statement}", f"- {section.safety_data_limitation_statement}"]
    for annotation in section.annotations:
        release = ", ".join(_markdown(item) for item in annotation.release_verification_states) or "not available"
        lines.extend(["", f"### Requested modality: {_markdown(annotation.requested_modality)}", "", f"- **Source:** {_markdown(annotation.source_name)} release {_markdown(annotation.source_release)}", f"- **Release verification state:** {release}", f"- **Annotation ID:** `{_markdown(annotation.annotation_id)}`", f"- **Feasibility profile ID:** `{_markdown(annotation.feasibility_profile_id)}`"])
        for label, field in (("Modality-specific observation references", "modality_specific_observation_ids"), ("Target-level contextual observation references", "target_context_observation_ids")):
            lines.append(f"- **{label}:**")
            for dimension, references in _references(annotation, field).items():
                text = ", ".join(f"`{_markdown(item)}`" for item in references) or "none retained"
                lines.append(f"  - {dimension}: {text}")
        lines.append("- **Coverage:**")
        for coverage in sorted(annotation.dimension_coverage, key=_coverage_key): lines.append(f"  - {_coverage_text(coverage)}")
        contradictions = ", ".join(f"`{_markdown(item)}`" for item in annotation.contradiction_observation_ids) or "none retained"
        lines.append(f"- **Contradictions retained without resolution:** {contradictions}")
        limitations = ", ".join(_markdown(item) for item in annotation.limitations) or "none retained"
        lines.append(f"- **Limitations:** {limitations}")
    return "\n".join(lines) + "\n"


def render_feasibility_html(section: FeasibilityReportSection) -> str:
    """Render the same descriptive content as escaped standalone HTML."""
    markdown = render_feasibility_markdown(section)
    return '<section class="card"><h2>Target feasibility — research-only</h2><pre class="note">' + html_escape(markdown) + "</pre></section>\n"

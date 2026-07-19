"""Focused contract tests for the versioned Open Targets normalization manifest."""
from dataclasses import FrozenInstanceError

import pytest

from targetintel.feasibility.opentargets_normalization import (
    NORMALIZATION_SCHEMA_ID,
    NORMALIZATION_SCHEMA_VERSION,
    OpenTargetsNormalizationManifest,
)


def test_normalization_manifest_has_stable_schema_and_canonical_serialization():
    manifest = OpenTargetsNormalizationManifest(source_release="24.06")
    duplicate = OpenTargetsNormalizationManifest(source_release="24.06")
    assert manifest.normalization_schema_id == NORMALIZATION_SCHEMA_ID
    assert manifest.normalization_schema_version == NORMALIZATION_SCHEMA_VERSION
    assert manifest.to_dict() == duplicate.to_dict()
    assert manifest.normalization_id == duplicate.normalization_id
    assert manifest.no_score_calculated and manifest.no_ranking_modified


def test_normalization_manifest_is_immutable_and_rejects_caller_mappings():
    manifest = OpenTargetsNormalizationManifest(source_release="24.06")
    with pytest.raises(FrozenInstanceError):
        manifest.source_release = "24.07"
    with pytest.raises(ValueError, match="unsupported normalization manifest"):
        OpenTargetsNormalizationManifest(source_release="24.06", modality_mapping_version="caller-defined")
    with pytest.raises(ValueError, match="unsupported normalization manifest"):
        OpenTargetsNormalizationManifest(source_release="24.06", allowed_source_fields=("arbitrary",))


def test_source_release_is_part_of_normalization_identity():
    assert (OpenTargetsNormalizationManifest(source_release="24.06").normalization_id
            != OpenTargetsNormalizationManifest(source_release="24.07").normalization_id)

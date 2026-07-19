"""Versioned, pure normalization rules for Issue 402 Open Targets records.

This module is deliberately a small allowlist.  It interprets no fields not
retained by the Issue 402 record contract and performs no I/O.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from types import MappingProxyType
from typing import Any, Mapping

from .models import canonical_json
from .opentargets_models import OpenTargetsTargetRecord, thaw

NORMALIZATION_SCHEMA_ID = "targetintel.opentargets-feasibility-normalization"
NORMALIZATION_SCHEMA_VERSION = "v0.4.0"
SUPPORTED_SOURCE_RECORD_VERSION = "v1"
DIMENSION_MAPPING_VERSION = "v1"
MODALITY_MAPPING_VERSION = "v1"
FACTOR_MAPPING_VERSION = "v1"
_ALLOWED_FIELDS = ("knownDrugs", "safetyLiabilities", "tractability")
_MODALITIES = {"ANTIBODY": "antibody", "SMALL MOLECULE": "small_molecule", "PROTAC": "protac",
               "OTHER": "other_clinical", "OTHER CLINICAL": "other_clinical"}


def _freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({str(key): _freeze(item) for key, item in value.items()})
    if isinstance(value, (tuple, list)):
        return tuple(_freeze(item) for item in value)
    return value


@dataclass(frozen=True)
class OpenTargetsNormalizationManifest:
    normalization_schema_id: str = NORMALIZATION_SCHEMA_ID
    normalization_schema_version: str = NORMALIZATION_SCHEMA_VERSION
    supported_source_record_version: str = SUPPORTED_SOURCE_RECORD_VERSION
    source_release: str = "not_reported"
    dimension_mapping_version: str = DIMENSION_MAPPING_VERSION
    modality_mapping_version: str = MODALITY_MAPPING_VERSION
    factor_mapping_version: str = FACTOR_MAPPING_VERSION
    allowed_source_fields: tuple[str, ...] = _ALLOWED_FIELDS
    no_score_calculated: bool = True
    no_ranking_modified: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(self, "allowed_source_fields", tuple(sorted(self.allowed_source_fields)))
        if (self.normalization_schema_id != NORMALIZATION_SCHEMA_ID
                or self.normalization_schema_version != NORMALIZATION_SCHEMA_VERSION
                or self.supported_source_record_version != SUPPORTED_SOURCE_RECORD_VERSION
                or self.dimension_mapping_version != DIMENSION_MAPPING_VERSION
                or self.modality_mapping_version != MODALITY_MAPPING_VERSION
                or self.factor_mapping_version != FACTOR_MAPPING_VERSION
                or tuple(sorted(self.allowed_source_fields)) != _ALLOWED_FIELDS
                or not self.no_score_calculated or not self.no_ranking_modified):
            raise ValueError("unsupported normalization manifest")

    @property
    def allowed_source_fields_hash(self) -> str:
        return sha256(canonical_json(list(self.allowed_source_fields)).encode("utf-8")).hexdigest()

    def identity_payload(self) -> dict[str, Any]:
        return {"normalization_schema_id": self.normalization_schema_id,
                "normalization_schema_version": self.normalization_schema_version,
                "supported_source_record_version": self.supported_source_record_version,
                "source_release": self.source_release,
                "dimension_mapping_version": self.dimension_mapping_version,
                "modality_mapping_version": self.modality_mapping_version,
                "factor_mapping_version": self.factor_mapping_version,
                "allowed_source_fields": list(self.allowed_source_fields),
                "allowed_source_fields_hash": self.allowed_source_fields_hash,
                "no_score_calculated": True, "no_ranking_modified": True}

    @property
    def normalization_id(self) -> str:
        return "otnorm_" + sha256(canonical_json(self.identity_payload()).encode("utf-8")).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        return {**self.identity_payload(), "normalization_id": self.normalization_id}


def manifest_for_record(record: OpenTargetsTargetRecord) -> OpenTargetsNormalizationManifest:
    if not isinstance(record, OpenTargetsTargetRecord) or record.record_format_version != SUPPORTED_SOURCE_RECORD_VERSION:
        raise ValueError("unsupported_source_record_version")
    return OpenTargetsNormalizationManifest(source_release=record.source_release)


def normalized_modality(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    return _MODALITIES.get(value.strip().upper())


def source_items(record: OpenTargetsTargetRecord, field: str) -> tuple[Any, ...] | None:
    """Return only an explicitly retained list field; malformed shapes fail closed."""
    if field not in record.source_fields:
        return None
    value = record.source_fields[field]
    # Issue 402's versioned target document exposes knownDrugs as a page
    # object.  Its rows are the only clinical-precedence records retained.
    if field == "knownDrugs" and isinstance(value, Mapping):
        value = value.get("rows")
    if not isinstance(value, tuple):
        raise ValueError("unsupported_source_shape")
    return value


def compact_value(value: Any, allowed_keys: tuple[str, ...]) -> Any:
    """Keep a small source-linked subset rather than duplicate raw payloads."""
    if not isinstance(value, Mapping):
        return value
    return _freeze({key: thaw(value[key]) for key in allowed_keys if key in value})

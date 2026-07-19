"""Pure construction of descriptive feasibility profiles from Issue 402 data."""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from types import MappingProxyType
from typing import Any, Mapping

from .models import (AVAILABILITY_STATES, OBSERVATION_FORMAT_VERSION, FeasibilityObservation,
                     TargetFeasibilityProfile, TargetFeasibilityRequest, canonical_json)
from .opentargets_models import OpenTargetsFetchResult, OpenTargetsTargetRecord, OpenTargetsTargetResolution, thaw
from .opentargets_normalization import (OpenTargetsNormalizationManifest, compact_value,
                                        manifest_for_record, normalized_modality, source_items)
from .validation import ValidationError, require_valid_profile, require_valid_request

_DIMENSION_ORDER = ("clinical_precedence", "tractability", "doability", "safety")
_MODALITY_ORDER = ("antibody", "small_molecule", "protac", "other_clinical")
_SUCCESS = frozenset({"built", "built_with_gaps"})


def _identity(prefix: str, payload: Mapping[str, Any]) -> str:
    return prefix + "_" + sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def _freeze(value: Any) -> Any:
    if isinstance(value, Mapping): return MappingProxyType({str(k): _freeze(v) for k, v in value.items()})
    if isinstance(value, (list, tuple)): return tuple(_freeze(v) for v in value)
    return value


@dataclass(frozen=True)
class FeasibilityDimensionCoverage:
    coverage_format_version: str
    target_identifier: str
    target_identifier_type: str
    dimension: str
    modality: str | None
    applicable_source_record_count: int
    observed_observation_count: int
    unavailable_count: int
    not_observed_count: int
    conflicting_count: int
    retrieval_failed_count: int
    unsupported_source_field_count: int
    coverage_state: str
    limitations: tuple[str, ...] | list[str] = ()

    def __post_init__(self) -> None:
        if self.dimension not in _DIMENSION_ORDER or (self.modality is not None and self.modality not in _MODALITY_ORDER):
            raise ValueError("unknown coverage dimension or modality")
        if self.coverage_state not in {"observed", "partial", "not_available", "not_applicable", "conflicting", "retrieval_failed"}:
            raise ValueError("unknown coverage state")
        if any(not isinstance(v, int) or v < 0 for v in (self.applicable_source_record_count, self.observed_observation_count,
                self.unavailable_count, self.not_observed_count, self.conflicting_count, self.retrieval_failed_count,
                self.unsupported_source_field_count)):
            raise ValueError("coverage counts must be non-negative integers")
        object.__setattr__(self, "limitations", tuple(sorted(set(self.limitations))))

    def identity_payload(self) -> dict[str, Any]:
        return {"coverage_format_version": self.coverage_format_version, "target_identifier": self.target_identifier,
                "target_identifier_type": self.target_identifier_type, "dimension": self.dimension, "modality": self.modality,
                "applicable_source_record_count": self.applicable_source_record_count, "observed_observation_count": self.observed_observation_count,
                "unavailable_count": self.unavailable_count, "not_observed_count": self.not_observed_count,
                "conflicting_count": self.conflicting_count, "retrieval_failed_count": self.retrieval_failed_count,
                "unsupported_source_field_count": self.unsupported_source_field_count, "coverage_state": self.coverage_state,
                "limitations": list(self.limitations), "not_scientific_confidence": True}
    @property
    def coverage_id(self) -> str: return _identity("tfdc", self.identity_payload())
    @property
    def coverage_is_scientific_confidence(self) -> bool: return False
    def to_dict(self) -> dict[str, Any]: return {**self.identity_payload(), "coverage_id": self.coverage_id}


def _coverage(request: TargetFeasibilityRequest, dimension: str, modality: str | None,
              observations: tuple[FeasibilityObservation, ...], applicable: int, limitations: tuple[str, ...] = (),
              unsupported: int = 0, retrieval_failed: int = 0) -> FeasibilityDimensionCoverage:
    # The overall tractability row deliberately includes every modality.  The
    # modality rows remain exact, so absent modality data stays visible rather
    # than being mistaken for an overall tractability conclusion.
    selected = tuple(item for item in observations if item.dimension == dimension
                     and (dimension == "tractability" and modality is None or item.modality == modality))
    counts = {state: sum(item.availability_state == state for item in selected) for state in AVAILABILITY_STATES}
    # Issue 401 deliberately detects contradictions from the explicit
    # observation fields, rather than requiring a producer to replace a
    # source observation's availability with ``conflicting``.  Retain that
    # distinction here: the source facts remain observed while coverage
    # records how many of those facts participate in a contradiction.
    groups: dict[tuple[Any, ...], list[FeasibilityObservation]] = {}
    for item in selected:
        key = (item.target_identifier, item.target_identifier_type, item.dimension,
               item.modality, item.factor_identifier, item.normalized_value_type)
        groups.setdefault(key, []).append(item)
    conflicting_ids: set[str] = set()
    for group in groups.values():
        values = {canonical_json(item.normalized_value) for item in group}
        if len(values) > 1 or any(item.availability_state == "conflicting" for item in group):
            conflicting_ids.update(item.observation_id for item in group)
    conflicting_count = len(conflicting_ids)
    if retrieval_failed: state = "retrieval_failed"
    elif conflicting_count: state = "conflicting"
    elif counts["observed"] and (unsupported or counts["not_available"]): state = "partial"
    elif counts["observed"]: state = "observed"
    elif counts["not_observed"] and not (unsupported or counts["not_available"]): state = "observed"
    elif applicable == 0 or counts["not_available"]: state = "not_available"
    else: state = "partial"
    return FeasibilityDimensionCoverage("v0.4.0", request.target_identifier, request.target_identifier_type, dimension, modality,
        applicable, counts["observed"], counts["not_available"], counts["not_observed"], conflicting_count,
        retrieval_failed + counts["retrieval_failed"], unsupported, state, limitations)


def _canonical_unordered(value: Any) -> Any:
    """Canonicalize source collections solely for semantic record identity."""
    if isinstance(value, Mapping):
        return {str(key): _canonical_unordered(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return sorted((_canonical_unordered(item) for item in value), key=canonical_json)
    return value


def _profile_source_record_identifier(record: OpenTargetsTargetRecord) -> str:
    """Return a source-record identity insensitive to source array ordering.

    Issue 402's raw record ID includes the retained response arrays.  That is
    useful retrieval provenance, but its value changes if an upstream source
    returns equivalent rows in another order.  Profile observations instead
    use this semantic identity; the raw Issue 402 record ID remains on the
    build result, where it is not part of profile identity.
    """
    payload = {
        "target_id": record.target_id,
        "ensembl_gene_id": record.ensembl_gene_id,
        "approved_symbol": record.approved_symbol,
        "approved_name": record.approved_name,
        "disease_id": record.disease_id,
        "association": _canonical_unordered(record.association),
        "source_fields": _canonical_unordered(record.source_fields),
        "source_release": record.source_release,
        "release_verification_state": record.release_verification_state,
        "source_query_id": record.source_query_id,
        "availability_state": record.availability_state,
        "limitations": sorted(record.limitations),
    }
    return _identity("otrecnorm", payload)


def _observation(request: TargetFeasibilityRequest, record: OpenTargetsTargetRecord, dimension: str, factor: str,
                 value: Any, value_type: str, availability: str = "observed", modality: str | None = None,
                 field: str = "") -> FeasibilityObservation:
    return FeasibilityObservation(OBSERVATION_FORMAT_VERSION, request.target_identifier, request.target_identifier_type,
        dimension, modality, factor, value, value_type, availability, request.source_name, request.source_release,
        _profile_source_record_identifier(record), field, {"source_record_identity": _profile_source_record_identifier(record), "source_query_id": record.source_query_id,
        "release_verification_state": record.release_verification_state}, ())


def _type(value: Any) -> str:
    if value is None: return "null"
    if isinstance(value, bool): return "boolean"
    if isinstance(value, (int, float)): return "number"
    if isinstance(value, str): return "string"
    if isinstance(value, tuple): return "array"
    return "object"


def _stable_factor_identifier(prefix: str, value: Mapping[str, Any], *identity_values: Any) -> str:
    """Use explicit source identity where present, otherwise a value fingerprint.

    Source arrays have no ordering contract.  Positional factor identifiers
    would therefore leak transport ordering into observation and profile
    identities.  The fallback is deliberately derived from the normalized
    source-linked value, not from an array position or external knowledge.
    """
    for identity_value in identity_values:
        if isinstance(identity_value, str) and identity_value.strip():
            return prefix + "_" + identity_value.strip()
    return prefix + "_" + sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _normalize(request: TargetFeasibilityRequest, record: OpenTargetsTargetRecord) -> tuple[tuple[FeasibilityObservation, ...], tuple[str, ...], Mapping[tuple[str, str | None], tuple[str, ...]], Mapping[tuple[str, str | None], int]]:
    observations: list[FeasibilityObservation] = []; limitations: list[str] = []
    scoped_limitations: dict[tuple[str, str | None], list[str]] = {}
    scoped_unsupported: dict[tuple[str, str | None], int] = {}
    def limit(key: tuple[str, str | None], value: str) -> None:
        scoped_limitations.setdefault(key, []).append(value)
    def unsupported(key: tuple[str, str | None]) -> None:
        scoped_unsupported[key] = scoped_unsupported.get(key, 0) + 1
    def unavailable(dimension: str, factor: str, field: str, modality: str | None = None) -> None:
        observations.append(_observation(request, record, dimension, factor, None, "null", "not_available", modality, field))
    unmapped = sorted(set(record.source_fields) - {"knownDrugs", "tractability", "safetyLiabilities"})
    if unmapped:
        limitations.extend("unmapped_source_field:" + field for field in unmapped)
    # Known-drug rows are descriptive clinical-precedence records, never validation.
    if "clinical_precedence" in request.requested_dimensions:
        items = source_items(record, "knownDrugs")
        if items is None:
            limit(("clinical_precedence", None), "clinical_precedence_source_field_not_retained")
            unavailable("clinical_precedence", "clinical_precedence_source_unavailable", "knownDrugs")
        else:
            for item in items:
                if not isinstance(item, Mapping): unsupported(("clinical_precedence", None)); continue
                drug = item.get("drug")
                value = {"drug": compact_value(drug, ("id", "name")),
                         "phase": item.get("phase", item.get("clinicalPhase")),
                         "status": item.get("status"),
                         "mechanism_of_action": item.get("mechanismOfAction"),
                         "disease_id": item.get("diseaseId")}
                drug_id = drug.get("id") if isinstance(drug, Mapping) else None
                drug_name = drug.get("name") if isinstance(drug, Mapping) else None
                factor = _stable_factor_identifier("known_drug", value, drug_id, drug_name)
                observations.append(_observation(request, record, "clinical_precedence", factor, value, "object", field="knownDrugs"))
            if not items:
                unavailable("clinical_precedence", "clinical_precedence_not_available", "knownDrugs")
    if "tractability" in request.requested_dimensions:
        items = source_items(record, "tractability")
        observed_modalities: set[str] = set()
        if items is None:
            limit(("tractability", None), "tractability_source_field_not_retained")
        else:
            for index, item in enumerate(items):
                if not isinstance(item, Mapping): unsupported(("tractability", None)); continue
                modality = normalized_modality(item.get("modality"))
                if modality is None:
                    unsupported(("tractability", None)); limit(("tractability", None), "unsupported_tractability_modality")
                    continue
                if modality not in request.requested_modalities: continue
                observed_modalities.add(modality)
                value = compact_value(item, ("label", "modality", "value"))
                observations.append(_observation(request, record, "tractability", str(item.get("label") or f"tractability_{index}"), value, "object", modality=modality, field="tractability"))
        for modality in request.requested_modalities:
            if modality not in observed_modalities:
                unavailable("tractability", "tractability_source_unavailable", "tractability", modality)
    # Issue 402 has no doability source field.  No inference is permitted.
    if "doability" in request.requested_dimensions:
        limit(("doability", None), "doability_not_retained_by_source_record_contract")
        unavailable("doability", "doability_source_unavailable", "doability")
    if "safety" in request.requested_dimensions:
        items = source_items(record, "safetyLiabilities")
        if items is None:
            limit(("safety", None), "safety_source_field_not_retained")
            unavailable("safety", "safety_source_unavailable", "safetyLiabilities")
        elif not items:
            # Scope is explicit: the source field was retrieved and empty, not a safety conclusion.
            observations.append(_observation(request, record, "safety", "retrieved_safety_liabilities", None, "null", "not_observed", field="safetyLiabilities"))
        else:
            for item in items:
                if not isinstance(item, Mapping): unsupported(("safety", None)); continue
                value = compact_value(item, ("id", "event", "effects", "biosamples", "datasource", "literature"))
                factor = _stable_factor_identifier("safety_liability", value, item.get("id"), item.get("event"))
                observations.append(_observation(request, record, "safety", factor, value, _type(value), field="safetyLiabilities"))
    return (tuple(observations), tuple(sorted(set(limitations))),
            MappingProxyType({key: tuple(sorted(set(values))) for key, values in scoped_limitations.items()}),
            MappingProxyType(dict(scoped_unsupported)))


def _resolution(request: TargetFeasibilityRequest, result: OpenTargetsFetchResult) -> OpenTargetsTargetResolution | None:
    matches = [r for r in result.resolutions if r.requested_identifier == request.target_identifier and r.requested_identifier_type == request.target_identifier_type]
    return matches[0] if len(matches) == 1 else None


def _valid_fetch_result(result: OpenTargetsFetchResult) -> bool:
    """Cheap structural guard; Issue 403 intentionally does not re-fetch data."""
    if result.result_format_version != "v1" or result.request.request_id != result.coverage_report.request_id:
        return False
    if len({item.resolution_id for item in result.resolutions}) != len(result.resolutions):
        return False
    if len({item.record_id for item in result.records}) != len(result.records):
        return False
    return all(isinstance(item, OpenTargetsTargetResolution) for item in result.resolutions) and all(isinstance(item, OpenTargetsTargetRecord) for item in result.records)


@dataclass(frozen=True)
class TargetFeasibilityProfileBuildResult:
    result_format_version: str; status: str; request_id: str; fetch_result_id: str; normalization_id: str | None
    target_resolution_id: str | None; target_record_id: str | None; profile: TargetFeasibilityProfile | None
    dimension_coverage: tuple[FeasibilityDimensionCoverage, ...] | list[FeasibilityDimensionCoverage]
    limitations: tuple[str, ...] | list[str] = (); error_codes: tuple[str, ...] | list[str] = ()
    no_score_calculated: bool = True; no_ranking_modified: bool = True
    def __post_init__(self) -> None:
        object.__setattr__(self, "dimension_coverage", tuple(sorted(self.dimension_coverage, key=lambda c: (_DIMENSION_ORDER.index(c.dimension), -1 if c.modality is None else _MODALITY_ORDER.index(c.modality), c.coverage_id))))
        object.__setattr__(self, "limitations", tuple(sorted(set(self.limitations))))
        object.__setattr__(self, "error_codes", tuple(sorted(set(self.error_codes))))
        if (self.status in _SUCCESS) != (self.profile is not None): raise ValueError("only successful results contain profiles")
        if not self.no_score_calculated or not self.no_ranking_modified: raise ValueError("result boundaries must remain true")
    @property
    def profile_id(self) -> str | None: return None if self.profile is None else self.profile.profile_id
    def identity_payload(self) -> dict[str, Any]: return {"result_format_version": self.result_format_version, "status": self.status, "request_id": self.request_id, "fetch_result_id": self.fetch_result_id, "normalization_id": self.normalization_id, "target_resolution_id": self.target_resolution_id, "target_record_id": self.target_record_id, "profile_id": self.profile_id, "coverage_ids": [c.coverage_id for c in self.dimension_coverage], "limitations": list(self.limitations), "error_codes": list(self.error_codes), "no_score_calculated": True, "no_ranking_modified": True}
    @property
    def result_id(self) -> str: return _identity("tfpr", self.identity_payload())
    def to_dict(self) -> dict[str, Any]: return {**self.identity_payload(), "result_id": self.result_id, "profile": None if self.profile is None else self.profile.to_dict(), "dimension_coverage": [c.to_dict() for c in self.dimension_coverage]}


def _empty_coverages(request: TargetFeasibilityRequest, retrieval_failed: bool = False) -> tuple[FeasibilityDimensionCoverage, ...]:
    keys = [(d, None) for d in request.requested_dimensions if d != "tractability"]
    if "tractability" in request.requested_dimensions: keys.append(("tractability", None)); keys.extend(("tractability", m) for m in request.requested_modalities)
    return tuple(_coverage(request, d, m, (), 0, retrieval_failed=retrieval_failed) for d, m in keys)


def build_target_feasibility_profile(request: TargetFeasibilityRequest, fetch_result: OpenTargetsFetchResult) -> TargetFeasibilityProfileBuildResult:
    """Build a profile with no transport, cache, scoring, ranking, or modality calls."""
    if not isinstance(request, TargetFeasibilityRequest): raise TypeError("request must be TargetFeasibilityRequest")
    if not isinstance(fetch_result, OpenTargetsFetchResult): raise TypeError("fetch_result must be OpenTargetsFetchResult")
    try: require_valid_request(request)
    except ValidationError: return TargetFeasibilityProfileBuildResult("v0.4.0", "invalid_request", request.request_id, fetch_result.result_id, None, None, None, None, _empty_coverages(request), error_codes=("invalid_request",))
    if request.source_name != "Open Targets" or not _valid_fetch_result(fetch_result):
        return TargetFeasibilityProfileBuildResult("v0.4.0", "invalid_fetch_result", request.request_id, fetch_result.result_id, None, None, None, None, _empty_coverages(request), error_codes=("invalid_fetch_result",))
    if fetch_result.release_verification_state == "mismatch" or fetch_result.status == "release_mismatch":
        return TargetFeasibilityProfileBuildResult("v0.4.0", "source_release_mismatch", request.request_id, fetch_result.result_id, None, None, None, None, _empty_coverages(request), error_codes=("source_release_mismatch",))
    resolution = _resolution(request, fetch_result)
    if resolution is None: return TargetFeasibilityProfileBuildResult("v0.4.0", "invalid_fetch_result", request.request_id, fetch_result.result_id, None, None, None, None, _empty_coverages(request), error_codes=("missing_or_duplicate_target_resolution",))
    if resolution.status != "resolved_exact":
        status = {"unresolved": "target_unresolved", "ambiguous": "target_ambiguous", "invalid_identifier": "target_invalid", "retrieval_failed": "target_retrieval_failed"}[resolution.status]
        return TargetFeasibilityProfileBuildResult("v0.4.0", status, request.request_id, fetch_result.result_id, None, resolution.resolution_id, None, None, _empty_coverages(request, status == "target_retrieval_failed"), error_codes=(status,))
    if (request.target_identifier_type == "ensembl_gene_id"
            and resolution.ensembl_gene_id != request.target_identifier):
        return TargetFeasibilityProfileBuildResult("v0.4.0", "target_invalid", request.request_id,
            fetch_result.result_id, None, resolution.resolution_id, None, None,
            _empty_coverages(request), error_codes=("ensembl_resolution_mismatch",))
    records = [r for r in fetch_result.records if r.ensembl_gene_id == resolution.ensembl_gene_id and (request.target_identifier_type != "gene_symbol" or r.approved_symbol == resolution.approved_symbol)]
    if len(records) != 1: return TargetFeasibilityProfileBuildResult("v0.4.0", "target_record_missing", request.request_id, fetch_result.result_id, None, resolution.resolution_id, None, None, _empty_coverages(request), error_codes=("target_record_missing",))
    record = records[0]
    if request.source_release != record.source_release:
        return TargetFeasibilityProfileBuildResult("v0.4.0", "source_release_mismatch", request.request_id, fetch_result.result_id, None, resolution.resolution_id, record.record_id, None, _empty_coverages(request), error_codes=("source_release_mismatch",))
    try:
        manifest = manifest_for_record(record)
        observations, global_limitations, scoped_limitations, scoped_unsupported = _normalize(request, record)
    except ValueError as exc:
        status = "unsupported_source_shape" if str(exc) == "unsupported_source_shape" else "normalization_failed"
        return TargetFeasibilityProfileBuildResult("v0.4.0", status, request.request_id, fetch_result.result_id, None, resolution.resolution_id, record.record_id, None, _empty_coverages(request), error_codes=(status,))
    if record.release_verification_state != "verified":
        global_limitations += ("source_release_not_verified",)
    limitations = tuple(sorted(set(global_limitations).union(
        limitation for values in scoped_limitations.values() for limitation in values
    )))
    coverage = []
    for dimension in request.requested_dimensions:
        if dimension == "tractability":
            coverage.append(_coverage(request, dimension, None, observations, 1,
                scoped_limitations.get((dimension, None), ()), scoped_unsupported.get((dimension, None), 0)))
            coverage.extend(_coverage(request, dimension, modality, observations, 1,
                scoped_limitations.get((dimension, modality), ()), scoped_unsupported.get((dimension, modality), 0))
                for modality in request.requested_modalities)
        else:
            coverage.append(_coverage(request, dimension, None, observations, 1,
                scoped_limitations.get((dimension, None), ()), scoped_unsupported.get((dimension, None), 0)))
    profile = TargetFeasibilityProfile.from_request(request, observations)
    try: require_valid_profile(profile, request)
    except ValidationError: return TargetFeasibilityProfileBuildResult("v0.4.0", "invalid_profile", request.request_id, fetch_result.result_id, manifest.normalization_id, resolution.resolution_id, record.record_id, None, coverage, limitations, ("invalid_profile",))
    status = "built_with_gaps" if limitations or any(c.coverage_state != "observed" for c in coverage) else "built"
    return TargetFeasibilityProfileBuildResult("v0.4.0", status, request.request_id, fetch_result.result_id, manifest.normalization_id, resolution.resolution_id, record.record_id, profile, coverage, limitations)


@dataclass(frozen=True)
class FeasibilityProfileBatchResult:
    batch_format_version: str; fetch_result_id: str; normalization_id: str | None; request_ids: tuple[str, ...] | list[str]; results: tuple[TargetFeasibilityProfileBuildResult, ...] | list[TargetFeasibilityProfileBuildResult]
    def __post_init__(self) -> None:
        object.__setattr__(self, "request_ids", tuple(sorted(self.request_ids))); object.__setattr__(self, "results", tuple(sorted(self.results, key=lambda r: r.request_id)))
    @property
    def dimension_coverage_totals(self) -> Mapping[str, int]:
        return MappingProxyType({dimension: sum(coverage.observed_observation_count for result in self.results for coverage in result.dimension_coverage if coverage.dimension == dimension and coverage.modality is None) for dimension in _DIMENSION_ORDER})
    @property
    def modality_tractability_coverage_totals(self) -> Mapping[str, int]:
        return MappingProxyType({modality: sum(coverage.observed_observation_count for result in self.results for coverage in result.dimension_coverage if coverage.dimension == "tractability" and coverage.modality == modality) for modality in _MODALITY_ORDER})
    @property
    def batch_id(self) -> str: return _identity("tfpb", {"batch_format_version": self.batch_format_version, "fetch_result_id": self.fetch_result_id, "normalization_id": self.normalization_id, "request_ids": list(self.request_ids), "result_ids": [r.result_id for r in self.results], "dimension_coverage_totals": dict(self.dimension_coverage_totals), "modality_tractability_coverage_totals": dict(self.modality_tractability_coverage_totals), "coverage_not_confidence": True})
    @property
    def requested_target_count(self) -> int: return len(self.request_ids)
    @property
    def built_target_count(self) -> int: return sum(r.status == "built" for r in self.results)
    @property
    def built_with_gaps_count(self) -> int: return sum(r.status == "built_with_gaps" for r in self.results)
    @property
    def unresolved_count(self) -> int: return sum(r.status == "target_unresolved" for r in self.results)
    @property
    def ambiguous_count(self) -> int: return sum(r.status == "target_ambiguous" for r in self.results)
    @property
    def missing_record_count(self) -> int: return sum(r.status == "target_record_missing" for r in self.results)
    @property
    def retrieval_failed_count(self) -> int: return sum(r.status == "target_retrieval_failed" for r in self.results)
    @property
    def coverage_is_scientific_confidence(self) -> bool: return False
    def to_dict(self) -> dict[str, Any]:
        return {"batch_format_version": self.batch_format_version, "batch_id": self.batch_id,
                "fetch_result_id": self.fetch_result_id, "normalization_id": self.normalization_id,
                "request_ids": list(self.request_ids), "result_ids": [item.result_id for item in self.results],
                "results": [item.to_dict() for item in self.results], "requested_target_count": self.requested_target_count,
                "built_target_count": self.built_target_count, "built_with_gaps_count": self.built_with_gaps_count,
                "unresolved_count": self.unresolved_count, "ambiguous_count": self.ambiguous_count,
                "missing_record_count": self.missing_record_count, "retrieval_failed_count": self.retrieval_failed_count,
                "dimension_coverage_totals": dict(self.dimension_coverage_totals),
                "modality_tractability_coverage_totals": dict(self.modality_tractability_coverage_totals),
                "coverage_is_scientific_confidence": False}


def build_target_feasibility_profiles(requests: tuple[TargetFeasibilityRequest, ...], fetch_result: OpenTargetsFetchResult) -> FeasibilityProfileBatchResult:
    if not isinstance(requests, tuple) or not all(isinstance(item, TargetFeasibilityRequest) for item in requests): raise TypeError("requests must be an immutable tuple of TargetFeasibilityRequest objects")
    request_ids = [item.request_id for item in requests]
    if len(request_ids) != len(set(request_ids)): raise ValueError("duplicate request IDs")
    results = tuple(build_target_feasibility_profile(item, fetch_result) for item in requests)
    normalization_ids = {item.normalization_id for item in results if item.normalization_id is not None}
    return FeasibilityProfileBatchResult("v0.4.0", fetch_result.result_id, next(iter(normalization_ids)) if len(normalization_ids) == 1 else None, request_ids, results)

"""Release-pinned, offline contracts for future DepMap functional-dependency work.

This package is intentionally limited to manifests and small-file validation.
It does not retrieve, parse, score, rank, classify, or interpret dependency data.
"""

from .depmap_models import (
    DepMapFileManifest,
    DepMapLocalLayoutRequest,
    DepMapReleaseManifest,
    DepMapSchemaFingerprint,
)
from .depmap_validation import DepMapManifestValidationResult, validate_local_release
from .depmap_ingestion import (
    DepMapIngestionError, DepMapIngestionRequest, DepMapIngestionSnapshot,
    DepMapTargetRequest, ingest_local_release, parse_gene_label,
)
from .depmap_profiles import (
    DepMapModelContextDefinition, DepMapProfileError,
    FunctionalDependencyProfile, FunctionalDependencyProfilePolicy,
    FunctionalDependencyProfileRun, build_dependency_profiles,
    write_dependency_profile_artifacts,
)
from .target_universes import (
    BenchmarkEntry, DiscoveryUniversePolicy, InclusionSourceRecord,
    TargetUniverse, TargetUniverseEntry, TargetUniverseFreezeManifest,
    freeze_universes,
)

__all__ = [
    "DepMapFileManifest",
    "DepMapLocalLayoutRequest",
    "DepMapManifestValidationResult",
    "DepMapReleaseManifest",
    "DepMapSchemaFingerprint",
    "validate_local_release",
    "DepMapIngestionError",
    "DepMapIngestionRequest",
    "DepMapIngestionSnapshot",
    "DepMapTargetRequest",
    "ingest_local_release",
    "parse_gene_label",
    "DepMapModelContextDefinition",
    "DepMapProfileError",
    "FunctionalDependencyProfile",
    "FunctionalDependencyProfilePolicy",
    "FunctionalDependencyProfileRun",
    "build_dependency_profiles",
    "write_dependency_profile_artifacts",
    "BenchmarkEntry",
    "DiscoveryUniversePolicy",
    "InclusionSourceRecord",
    "TargetUniverse",
    "TargetUniverseEntry",
    "TargetUniverseFreezeManifest",
    "freeze_universes",
]

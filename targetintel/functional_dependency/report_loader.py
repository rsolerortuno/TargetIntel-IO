"""Offline loader for the sanitized DepMap report publication bundle.

The loader deliberately has a much narrower boundary than the local DepMap
workflow: it reads the checked, aggregate report records only.  In particular
it never follows provenance into a run directory or a raw release download.
"""
from __future__ import annotations

from collections import OrderedDict
from hashlib import sha256
import json
from pathlib import Path
import re
from types import MappingProxyType
from typing import Mapping, Iterable

from .report_contract import DependencyReportEvidence


_REQUIRED = {"release_summary.json", "publication_manifest.json", "source_manifest.json", "checksums.json", "dependency_report_evidence.jsonl"}
_IDENTITIES = {
    "release_identifier": "DepMap_Public_26Q1",
    "release_manifest_id": "dmrm_08d15741ac2297df953346ff257dec05feb0b754a62ae6a9f56573e11801c5b1",
    "configuration_id": "v050rc_fe68644624acd4b72aaf289baa9380c07f30d26c3271923ba81540f9b91e37b6",
    "scientific_closure_identity": "v050closure_e57fa135ff266078d2170bf2a34df094f7888e7ce6002783c75f6a583690a3a4",
    "context_identity": "melanoma_anti_pd1:v1",
}
_PATH_LEAK = re.compile(r"(?:/home/|/media/|/mnt/|/tmp/|/Users/|/Volumes/|(?:^|[^A-Za-z])[A-Za-z]:[\\/]|\brso12\b|\bS6445-MD61213\b|\b5EC8-12FA\b|\b[0-9A-F]{4}-[0-9A-F]{4}\b)", re.I)


class DependencyReportLoaderError(ValueError):
    """A portable bundle failed its publication contract."""


def _read_json(path: Path) -> object:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise DependencyReportLoaderError("portable publication JSON is malformed") from exc


def _validate_checksum_inventory(root: Path) -> None:
    inventory = _read_json(root / "checksums.json")
    rows = inventory.get("artifacts") if isinstance(inventory, dict) else inventory
    if not isinstance(rows, list):
        raise DependencyReportLoaderError("checksums inventory is malformed")
    seen: set[str] = set()
    for row in rows:
        if not isinstance(row, dict) or not {"name", "sha256", "byte_size"} <= set(row):
            raise DependencyReportLoaderError("checksums inventory entry is malformed")
        name = row["name"]
        if not isinstance(name, str) or name in seen or "/" in name or "\\" in name:
            raise DependencyReportLoaderError("checksums inventory contains an unsafe name")
        seen.add(name)
        path = root / name
        if not path.is_file() or path.stat().st_size != row["byte_size"]:
            raise DependencyReportLoaderError("portable publication checksum size mismatch")
        if sha256(path.read_bytes()).hexdigest() != row["sha256"]:
            raise DependencyReportLoaderError("portable publication checksum mismatch")
    if not _REQUIRED <= seen | {"checksums.json"}:
        raise DependencyReportLoaderError("checksums inventory omits a required artifact")


def _validate_identities(summary: object, manifest: object) -> None:
    if not isinstance(summary, dict) or not isinstance(manifest, dict):
        raise DependencyReportLoaderError("publication identity artifact is malformed")
    for name, expected in _IDENTITIES.items():
        if summary.get(name) != expected or manifest.get(name) != expected:
            raise DependencyReportLoaderError("portable publication identity mismatch: " + name)
    if manifest.get("publication_format_version") != "v1":
        raise DependencyReportLoaderError("unsupported publication format")


def load_dependency_report_evidence_bundle(snapshot_dir: str | Path, target_symbols: Iterable[str] | None = None) -> Mapping[str, DependencyReportEvidence]:
    """Load validated immutable evidence, without raw DepMap data access.

    ``target_symbols`` is an optional deterministic selection. Unknown names
    are rejected rather than silently treated as unavailable profiles.
    """
    root = Path(snapshot_dir)
    if not root.is_dir() or root.is_symlink() or any(part.is_symlink() for part in (root, *root.parents)):
        raise DependencyReportLoaderError("snapshot directory is unsafe")
    if not _REQUIRED <= {path.name for path in root.iterdir() if path.is_file()}:
        raise DependencyReportLoaderError("portable publication is incomplete")
    for path in root.rglob("*"):
        if path.is_file() and path.suffix in {".json", ".tsv", ".md", ".html", ".jsonl"}:
            if _PATH_LEAK.search(path.read_text(encoding="utf-8")):
                raise DependencyReportLoaderError("portable publication contains local operational metadata")
    _validate_checksum_inventory(root)
    summary = _read_json(root / "release_summary.json")
    manifest = _read_json(root / "publication_manifest.json")
    source_manifest = _read_json(root / "source_manifest.json")
    _validate_identities(summary, manifest)
    if not isinstance(source_manifest, dict) or source_manifest.get("source_project") != "DepMap":
        raise DependencyReportLoaderError("source manifest is malformed")
    for name, expected in _IDENTITIES.items():
        if source_manifest.get(name) != expected:
            raise DependencyReportLoaderError("source manifest identity mismatch: " + name)
    records: dict[str, DependencyReportEvidence] = {}
    try:
        lines = (root / "dependency_report_evidence.jsonl").read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError) as exc:
        raise DependencyReportLoaderError("portable evidence records cannot be read") from exc
    for line in lines:
        if not line.strip():
            continue
        if _PATH_LEAK.search(line):
            raise DependencyReportLoaderError("portable evidence contains a local path")
        try:
            evidence = DependencyReportEvidence.from_dict(json.loads(line))
        except (json.JSONDecodeError, TypeError, ValueError) as exc:
            raise DependencyReportLoaderError("portable evidence record is invalid") from exc
        for name, expected in _IDENTITIES.items():
            if getattr(evidence, name) != expected:
                raise DependencyReportLoaderError("evidence identity mismatch: " + name)
        if evidence.gene_symbol in records:
            raise DependencyReportLoaderError("duplicate portable evidence gene")
        records[evidence.gene_symbol] = evidence
    requested = None if target_symbols is None else tuple(target_symbols)
    if requested is not None:
        if any(not isinstance(symbol, str) or not symbol for symbol in requested):
            raise DependencyReportLoaderError("target symbols must be non-empty strings")
        unknown = sorted(set(requested) - set(records))
        if unknown:
            raise DependencyReportLoaderError("unknown target symbols: " + ",".join(unknown))
        records = {symbol: records[symbol] for symbol in sorted(set(requested))}
    return MappingProxyType(OrderedDict((symbol, records[symbol]) for symbol in sorted(records)))

"""Deterministic, repository-safe publication of a completed DepMap closure."""
from __future__ import annotations

import csv
from hashlib import sha256
import json
from pathlib import Path
import re
import shutil
import tempfile
from typing import Any, Iterable, Mapping

from .report_contract import build_dependency_report_evidence
from .report_snapshot import export_depmap_report_snapshot

IDENTITIES = {
    "release_identifier": "DepMap_Public_26Q1",
    "release_manifest_id": "dmrm_08d15741ac2297df953346ff257dec05feb0b754a62ae6a9f56573e11801c5b1",
    "configuration_id": "v050rc_fe68644624acd4b72aaf289baa9380c07f30d26c3271923ba81540f9b91e37b6",
    "scientific_closure_identity": "v050closure_e57fa135ff266078d2170bf2a34df094f7888e7ce6002783c75f6a583690a3a4",
    "context_identity": "melanoma_anti_pd1:v1",
}
FORBIDDEN_NAMES = re.compile(r"(?:CRISPRGeneEffect|CRISPRGeneDependency|Model\.csv|ScreenGeneEffect|ScreenGeneDependency|dependency_profiles\.jsonl|\.parquet$|\.h5$|\.h5ad$|\.rds$|\.loom$|\.mtx$|\.tar(?:\.gz)?$|\.zip$)", re.I)
# These are deliberately value-based checks.  Publication must not depend on
# the machine which ran the closure in order to know which local operational
# identifiers to remove.
PATH_LEAK = re.compile(r"(?:/home/|/media/|/mnt/|/tmp/|/Users/|/Volumes/|(?:^|[^A-Za-z])[A-Za-z]:[\\/]|\brso12\b|\bS6445-MD61213\b|\b5EC8-12FA\b|\b[0-9A-F]{4}-[0-9A-F]{4}\b)", re.I)
# A drive-letter path may occur within prose, but a POSIX operational path must
# begin at a path boundary.  In particular, do not treat the ``s://`` portion
# of an HTTPS URL as a local path.
_LOCAL_PATH_VALUE = re.compile(r"(?:\b[A-Za-z]:[\\/][^\s`'\"<>]+|(?<![A-Za-z0-9+.-])/(?:home|media|mnt|tmp|Users|Volumes)/[^\s`'\"<>]+)")
_SYNTHETIC_FIXTURE_LIMITATION = "Descriptive synthetic-fixture evidence only; no therapeutic, clinical, safety, or causal conclusion."
_REAL_RELEASE_LIMITATION = "Descriptive real-release aggregate evidence only; no therapeutic, clinical, safety, or causal conclusion."


class DepMapPublicationError(ValueError):
    pass


def _json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise DepMapPublicationError("required validated artifact is malformed") from exc
    if not isinstance(data, dict):
        raise DepMapPublicationError("required validated artifact must be an object")
    return data


def _sha(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def _assert_safe_output(output: Path, inputs: Iterable[Path]) -> None:
    if output == Path("/") or output.is_symlink() or any(p.is_symlink() for p in (output, *output.parents)):
        raise DepMapPublicationError("unsafe publication output")
    for source in inputs:
        if output == source or output.is_relative_to(source) or source.is_relative_to(output):
            raise DepMapPublicationError("publication output overlaps an input")


def _profiles(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    try:
        with path.open(encoding="utf-8") as handle:
            for line in handle:
                if line.strip(): rows.append(json.loads(line))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise DepMapPublicationError("validated dependency profiles are malformed") from exc
    symbols = [row.get("target_identity", {}).get("normalized_request") for row in rows]
    if len(rows) != 331 or any(not isinstance(symbol, str) or not symbol for symbol in symbols) or len(set(symbols)) != 331:
        raise DepMapPublicationError("validated discovery universe must contain exactly 331 unique identities")
    return sorted(rows, key=lambda row: row["target_identity"]["normalized_request"])


def _attach_frozen_canonical_identities(profiles: list[dict[str, Any]], universe_path: Path) -> None:
    """Supply the frozen discovery identity omitted by profile payloads."""
    if not universe_path.is_file():
        return
    with universe_path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle, delimiter="\t"))
    identities = {row.get("original_identifier"): row.get("canonical_identity") for row in rows}
    for profile in profiles:
        target = profile.get("target_identity")
        if not isinstance(target, dict):
            raise DepMapPublicationError("validated dependency profile target identity is malformed")
        symbol = target.get("normalized_request")
        canonical = identities.get(symbol)
        if canonical is not None:
            target["canonical_identity"] = canonical


def _replace_fixture_limitation(profiles: list[dict[str, Any]]) -> None:
    """Correct inherited fixture wording only in the portable real-release view.

    The validated profile calculation remains untouched.  This publication-time
    correction prevents an inherited fixture label from being represented as a
    property of the real DepMap release.
    """
    for profile in profiles:
        payload = profile.get("payload")
        if not isinstance(payload, dict):
            continue
        limitations = payload.get("limitations")
        if isinstance(limitations, list):
            payload["limitations"] = [
                _REAL_RELEASE_LIMITATION if item == _SYNTHETIC_FIXTURE_LIMITATION else item
                for item in limitations
            ]


def _overlay(path: Path) -> dict[str, dict[str, Any]]:
    with path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle, delimiter="\t"))
    result: dict[str, dict[str, Any]] = {}
    for row in rows:
        symbol = row.get("original_target_identifier") or row.get("target")
        if symbol:
            result[symbol] = {key: (int(value) if key in {"baseline_rank", "candidate_rank"} and value and value.lstrip("-").isdigit() else value or None) for key, value in row.items()}
    return result


def _source_files(preflight: Mapping[str, Any]) -> list[dict[str, Any]]:
    candidates = preflight.get("source_files") or preflight.get("input_files") or preflight.get("release_files")
    if not isinstance(candidates, list):
        raise DepMapPublicationError("validated release does not declare source filenames and checksums")
    result = []
    for item in candidates:
        if not isinstance(item, Mapping): raise DepMapPublicationError("source manifest entry is malformed")
        name = item.get("filename") or item.get("name")
        checksum = item.get("sha256") or item.get("checksum")
        size = item.get("byte_size") or item.get("size")
        if not isinstance(name, str) or not isinstance(checksum, str) or not isinstance(size, int):
            raise DepMapPublicationError("source manifest lacks filename, checksum, or size")
        result.append({"filename": name, "sha256": checksum, "byte_size": size, "role": item.get("role", "validated DepMap input")})
    return sorted(result, key=lambda value: value["filename"])


def _source_files_from_checksums(manifests: Path) -> list[dict[str, Any]]:
    """Read the validated download checksum ledger when preflight is concise."""
    path = manifests / "downloaded_files.sha256.tsv"
    if not path.is_file():
        raise DepMapPublicationError("validated release does not declare source filenames and checksums")
    with path.open(encoding="utf-8", newline="") as handle:
        values = list(csv.reader(handle, delimiter="\t"))
    if values and values[0] == ["filename", "bytes", "sha256"]:
        values = values[1:]
    result = []
    for row in values:
        if len(row) != 3:
            raise DepMapPublicationError("source checksum ledger is malformed")
        name, size, checksum = row
        if not isinstance(name, str) or not re.fullmatch(r"[0-9a-f]{64}", checksum or "") or not str(size).isdigit():
            raise DepMapPublicationError("source checksum ledger is malformed")
        role = {
            "CRISPRGeneEffect.csv": "CRISPR gene-effect matrix",
            "CRISPRGeneDependency.csv": "CRISPR dependency-probability matrix",
            "Model.csv": "model metadata",
        }.get(name, "validated DepMap release input")
        result.append({"filename": name, "sha256": checksum, "byte_size": int(size), "role": role})
    if not result:
        raise DepMapPublicationError("source checksum ledger is empty")
    return sorted(result, key=lambda value: value["filename"])


def _sanitize_text(text: str) -> str:
    """Remove operational locations and identifiers without changing science."""
    text = _LOCAL_PATH_VALUE.sub("<LOCAL_PATH_REMOVED>", text)
    return PATH_LEAK.sub("<OPERATIONAL_IDENTIFIER_REMOVED>", text)


def _sanitize_tree(root: Path) -> None:
    for path in root.rglob("*"):
        if path.is_file() and path.suffix in {".json", ".tsv", ".md", ".html", ".jsonl"}:
            text = path.read_text(encoding="utf-8")
            sanitized = _sanitize_text(text)
            if sanitized != text:
                path.write_text(sanitized, encoding="utf-8", newline="")


def validate_publication_tree(root: Path, *, bundle_limit: bool = True) -> None:
    """Validate portable content and size boundaries without reading any raw data."""
    total = 0
    for path in root.rglob("*"):
        if not path.is_file(): continue
        if FORBIDDEN_NAMES.search(path.name) or any(part in {"raw", "cache"} for part in path.relative_to(root).parts):
            raise DepMapPublicationError("forbidden raw artifact in publication output")
        size = path.stat().st_size; total += size
        if size > 5 * 1024 * 1024: raise DepMapPublicationError("publication data artifact exceeds 5 MiB")
        if path.suffix == ".html" and size > 2 * 1024 * 1024: raise DepMapPublicationError("publication HTML exceeds 2 MiB")
        if path.suffix in {".json", ".tsv", ".md", ".html", ".jsonl"} and PATH_LEAK.search(path.read_text(encoding="utf-8")):
            raise DepMapPublicationError("publication output contains a local path")
    if bundle_limit and total > 30 * 1024 * 1024: raise DepMapPublicationError("publication bundle exceeds 30 MiB")


def _copy_useful_closure_artifacts(run: Path, config: Path, manifests: Path, destination: Path) -> None:
    """Retain every small closure state artifact under stable portable names."""
    sources = {
        "release_preflight.json": run / "release_preflight.json",
        "artifact_compatibility.json": run / "artifact_compatibility.json",
        "reproducibility_summary.json": run / "reproducibility_summary.json",
        "release_readiness.json": run / "release_readiness.json",
        "activation_readiness_summary.json": run / "activation_readiness_summary.json",
        "baseline_preservation.json": run / "integration" / "baseline_preservation.json",
        "integration_gate_decision.json": run / "integration" / "integration_gate_decision.json",
        "benchmark_coverage.json": run / "benchmark" / "benchmark_coverage.json",
        "benchmark_universe.tsv": run / "universes" / "benchmark_universe.tsv",
        "discovery_universe.tsv": run / "universes" / "discovery_universe.tsv",
        "release_closure_manifest.json": run / "release_closure_manifest.json",
        "release_configuration_identity.json": config / "release_configuration_identity.json",
    }
    for name, source in sources.items():
        if source.is_file() and source.stat().st_size <= 5 * 1024 * 1024:
            shutil.copyfile(source, destination / name)


def _source_inventory(run: Path, config: Path, manifests: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    roots = (("run", run, sorted(run.rglob("*"))), ("manifest", manifests, sorted(manifests.rglob("*"))))
    # A real publication may use the repository root as ``config_dir``. Only
    # identity artifacts are closure candidates; traversing the repository (or
    # its .git directory) would make inventory depend on unrelated work.
    config_files = [config / name for name in ("release_configuration_identity.json", "real_run_config.json")]
    for label, root, paths in (*roots, ("config", config, config_files)):
        for path in paths:
            if not path.is_file():
                continue
            name = f"{label}/{path.relative_to(root).as_posix()}"
            raw = bool(FORBIDDEN_NAMES.search(path.name) or any(part in {"raw", "cache"} for part in path.relative_to(root).parts))
            rows.append({"source_artifact_name": name, "artifact_category": "raw_or_redistributable" if raw else "closure_artifact", "source_size": path.stat().st_size, "source_checksum": _sha(path), "publication_action": "excluded", "exclusion_reason": "raw or redistributable DepMap source data" if raw else "not a repository-safe aggregate publication artifact", "published_relative_path": "", "published_checksum": ""})
    return rows


def _read_ranked_targets(path: Path) -> set[str]:
    try:
        with path.open(encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle, delimiter="\t" if path.suffix == ".tsv" else ","))
    except (OSError, UnicodeError, csv.Error) as exc:
        raise DepMapPublicationError("ranked targets are malformed") from exc
    # The immutable integration overlay is an accepted explicit baseline
    # source for publication.  It labels the same stable symbol field
    # ``original_target_identifier`` rather than ``target_symbol``.
    symbols = [row.get("target_symbol") or row.get("original_target_identifier") for row in rows]
    if len(symbols) != 300 or any(not isinstance(symbol, str) or not symbol for symbol in symbols) or len(set(symbols)) != 300:
        raise DepMapPublicationError("productive baseline must contain exactly 300 unique targets")
    return set(symbols)


def _validated_counts(run: Path) -> dict[str, int]:
    compatibility = _json(run / "artifact_compatibility.json")
    metrics = compatibility.get("metrics")
    coverage = _json(run / "benchmark" / "benchmark_coverage.json")
    if not isinstance(metrics, Mapping):
        raise DepMapPublicationError("validated aggregate counts are missing")
    counts = {
        "benchmark_count": coverage.get("total_benchmark_targets", metrics.get("benchmark_count")),
        "discovery_count": metrics.get("discovery_count"),
        "background_count": metrics.get("background_count"),
    }
    expected = {"benchmark_count": 56, "discovery_count": 331, "background_count": 18531}
    if counts != expected:
        raise DepMapPublicationError("validated aggregate universe count mismatch")
    return {name: int(value) for name, value in counts.items()}


def publish_depmap_v050(*, run_dir: str | Path, config_dir: str | Path, manifest_dir: str | Path, output_dir: str | Path, ranked_targets: str | Path) -> Path:
    """Publish only derived aggregate records from an already validated closure."""
    run, config, manifests, output = (Path(value).resolve() for value in (run_dir, config_dir, manifest_dir, output_dir))
    ranked_path = Path(ranked_targets).resolve()
    if not all(path.is_dir() for path in (run, config, manifests)) or not ranked_path.is_file():
        raise DepMapPublicationError("explicit validated inputs are required")
    # ``config_dir`` may be the repository root, so it is deliberately not an
    # overlap guard. It is read-only input; the run and manifest roots contain
    # the validated closure and must never overlap publication output.
    _assert_safe_output(output, (run, manifests))
    productive_symbols = _read_ranked_targets(ranked_path)
    preflight = _json(run / "release_preflight.json")
    for key, expected in IDENTITIES.items():
        if key in {"scientific_closure_identity", "context_identity"}: continue
        if preflight.get(key) != expected: raise DepMapPublicationError("validated release identity mismatch: " + key)
    closure = _json(run / "release_closure_manifest.json")
    closure_summary = _json(manifests / "real-v6-release-closure-summary.json")
    reproducibility = _json(run / "reproducibility_summary.json")
    reproducible_identity = reproducibility.get("excluded_artifact_invariants", {}).get("closure_scientific_identity", {})
    if isinstance(reproducible_identity, Mapping) and reproducible_identity.get("first") != reproducible_identity.get("second"):
        raise DepMapPublicationError("validated release has inconsistent scientific closure identities")
    closure_identity = closure.get("scientific_closure_identity", closure.get("closure_scientific_identity", closure_summary.get("scientific_closure_identity", reproducible_identity.get("first") if isinstance(reproducible_identity, Mapping) else None)))
    if closure_identity != IDENTITIES["scientific_closure_identity"]:
        raise DepMapPublicationError("validated release identity mismatch: scientific_closure_identity")
    profiles = _profiles(run / "profiles" / "dependency_profiles.jsonl")
    _attach_frozen_canonical_identities(profiles, run / "universes" / "discovery_universe.tsv")
    _replace_fixture_limitation(profiles)
    source_files = _source_files(preflight) if any(key in preflight for key in ("source_files", "input_files", "release_files")) else _source_files_from_checksums(manifests)
    overlay = _overlay(run / "integration" / "candidate_overlay.tsv")
    if set(overlay) != productive_symbols:
        raise DepMapPublicationError("validated overlay and productive baseline targets differ")
    counts = _validated_counts(run)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=".depmap-publication-", dir=output.parent))
    try:
        # Issue 508 remains the sole snapshot exporter.  Its selected-output
        # table is replaced below with the complete discovery aggregate table.
        # The release configuration supplied for real publication is the
        # repository root. The exporter needs only its frozen identity, so use
        # an ephemeral identity-only view rather than modifying that input.
        export_config = temporary / "export_config"
        export_config.mkdir()
        (export_config / "release_configuration_identity.json").write_text(json.dumps({"configuration_id": IDENTITIES["configuration_id"]}), encoding="utf-8")
        export_depmap_report_snapshot(run_dir=run, config_dir=export_config, manifest_dir=manifests,
            output_dir=temporary / "snapshot", selected_targets=[p["target_identity"]["normalized_request"] for p in profiles])
        shutil.rmtree(export_config)
        for item in (temporary / "snapshot").iterdir(): shutil.move(str(item), temporary / item.name)
        (temporary / "snapshot").rmdir()
        _copy_useful_closure_artifacts(run, config, manifests, temporary)
        summary = _json(temporary / "release_summary.json")
        if summary.get("context_identity") != IDENTITIES["context_identity"]:
            raise DepMapPublicationError("validated release identity mismatch: context_identity")
        summary.update(IDENTITIES)
        summary.update({"productive_baseline_count": len(productive_symbols), **counts})
        (temporary / "release_summary.json").write_text(json.dumps(summary, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
        evidence = []
        for profile in profiles:
            symbol = profile["target_identity"]["normalized_request"]
            record = build_dependency_report_evidence(release_summary=summary, profile_record=profile,
                overlay_record=overlay.get(symbol), provenance={"source_artifact_names": ["selected_target_profiles.tsv", "candidate_overlay.tsv"]})
            evidence.append(record)
        (temporary / "dependency_report_evidence.jsonl").write_text("".join(item.canonical_json() + "\n" for item in evidence), encoding="utf-8")
        with (temporary / "selected_target_profiles.tsv").open("w", encoding="utf-8", newline="") as handle:
            fields = ["target", "canonical_gene_identity", "profile_available", "coverage_status", "context_model_count", "reference_model_count", "gene_effect", "dependency_probability", "context_reference_comparison", "selectivity", "interpretation_state", "portable_provenance"]
            writer = csv.DictWriter(handle, fieldnames=fields, delimiter="\t"); writer.writeheader()
            for item in evidence:
                record = item.to_dict()
                writer.writerow({"target": item.gene_symbol, "canonical_gene_identity": item.canonical_gene_identity or "", "profile_available": str(item.profile_available).lower(), "coverage_status": item.coverage_status, "context_model_count": item.context_model_count if item.context_model_count is not None else "", "reference_model_count": item.reference_model_count if item.reference_model_count is not None else "", "gene_effect": json.dumps(record["gene_effect"] or {}, sort_keys=True), "dependency_probability": json.dumps(record["dependency_probability"] or {}, sort_keys=True), "context_reference_comparison": json.dumps(record["context_reference_comparison"] or {}, sort_keys=True), "selectivity": json.dumps(record["selectivity"] or {}, sort_keys=True), "interpretation_state": item.dependency_interpretation_state or "", "portable_provenance": ";".join(item.provenance["source_artifact_names"])})
        source_manifest = {"source_project": "DepMap", "source_release": "DepMap Public 26Q1", "official_download_url": "https://depmap.org/portal/data_page/?release=DepMap+Public+26Q1", "official_release_notes_url": "https://forum.depmap.org/t/announcing-the-26q1-release/4606", "source_files": source_files, **IDENTITIES, "derivation": "Validated aggregate functional-dependency closure; no recalculation.", "redistributability_boundary": "Raw DepMap matrices are not committed."}
        (temporary / "source_manifest.json").write_text(json.dumps(source_manifest, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
        manifest = {"publication_format_version": "v1", **IDENTITIES, "selected_target_profile_count": len(profiles), "productive_baseline_count": len(productive_symbols), **counts, "raw_matrices_committed": False}
        (temporary / "publication_manifest.json").write_text(json.dumps(manifest, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
        _sanitize_tree(temporary)
        candidates = [path for path in temporary.iterdir() if path.is_file()]
        inventory = _source_inventory(run, config, manifests)
        with (
            temporary / "publication_inventory.tsv"
        ).open(
            "w",
            encoding="utf-8",
            newline="",
        ) as handle:
            fields = [
                "source_artifact_name",
                "artifact_category",
                "source_size",
                "source_checksum",
                "publication_action",
                "exclusion_reason",
                "published_relative_path",
                "published_checksum",
            ]
            writer = csv.DictWriter(
                handle,
                fieldnames=fields,
                delimiter="\t",
                quoting=csv.QUOTE_ALL,
                lineterminator="\n",
            )
            writer.writeheader()

            for candidate in sorted(candidates):
                writer.writerow(
                    {
                        "source_artifact_name": candidate.name,
                        "artifact_category": "derived_aggregate",
                        "source_size": candidate.stat().st_size,
                        "source_checksum": _sha(candidate),
                        "publication_action": "published",
                        "exclusion_reason": "",
                        "published_relative_path": candidate.name,
                        "published_checksum": _sha(candidate),
                    }
                )

            for row in inventory:
                writer.writerow(row)

            for source in source_files:
                writer.writerow(
                    {
                        "source_artifact_name": source["filename"],
                        "artifact_category": "raw_source",
                        "source_size": source["byte_size"],
                        "source_checksum": source["sha256"],
                        "publication_action": "excluded",
                        "exclusion_reason": (
                            "raw or redistributable DepMap source data"
                        ),
                        "published_relative_path": "",
                        "published_checksum": "",
                    }
                )
        checksums = [{"name": path.name, "sha256": _sha(path), "byte_size": path.stat().st_size} for path in sorted(temporary.iterdir()) if path.is_file() and path.name != "checksums.json"]
        (temporary / "checksums.json").write_text(json.dumps({"artifacts": checksums}, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
        _sanitize_tree(temporary)
        validate_publication_tree(temporary)
        if output.exists(): shutil.rmtree(output)
        temporary.replace(output)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True); raise
    return output

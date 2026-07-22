from __future__ import annotations

from hashlib import sha256
import json
import pytest

from targetintel.functional_dependency.report_loader import DependencyReportLoaderError, load_dependency_report_evidence_bundle
from test_depmap_v050_publication import published_bundle


def test_loader_is_deterministic_and_selectable(published_bundle: Path) -> None:
    first = load_dependency_report_evidence_bundle(published_bundle)
    assert len(first) == 331 and list(first) == sorted(first)
    assert list(load_dependency_report_evidence_bundle(published_bundle, ["G002", "G000"])) == ["G000", "G002"]
    with pytest.raises(DependencyReportLoaderError, match="unknown target"):
        load_dependency_report_evidence_bundle(published_bundle, ["MISSING"])


def test_loader_rejects_checksum_and_duplicate_records(published_bundle: Path) -> None:
    evidence = published_bundle / "dependency_report_evidence.jsonl"
    evidence.write_text(evidence.read_text() + evidence.read_text().splitlines()[0] + "\n")
    with pytest.raises(DependencyReportLoaderError):
        load_dependency_report_evidence_bundle(published_bundle)
    checksums = published_bundle / "checksums.json"
    rows = json.loads(checksums.read_text())["artifacts"]
    for row in rows:
        if row["name"] == evidence.name:
            row["byte_size"] = evidence.stat().st_size
            row["sha256"] = sha256(evidence.read_bytes()).hexdigest()
    checksums.write_text(json.dumps({"artifacts": rows}, sort_keys=True, separators=(",", ":")) + "\n")
    with pytest.raises(DependencyReportLoaderError, match="duplicate"):
        load_dependency_report_evidence_bundle(published_bundle)

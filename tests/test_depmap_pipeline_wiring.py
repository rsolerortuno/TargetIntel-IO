from __future__ import annotations

import inspect
from types import SimpleNamespace

from targetintel.cli import build_parser
import targetintel.pipeline as pipeline_module
from targetintel.pipeline import (
    _report_dependency_coverage,
    run_core_pipeline,
    run_pipeline,
)


def test_pipeline_and_cli_make_the_snapshot_strictly_optional() -> None:
    assert inspect.signature(run_core_pipeline).parameters["depmap_snapshot_path"].default is None
    assert inspect.signature(run_pipeline).parameters["depmap_snapshot_path"].default is None
    assert build_parser().parse_args(["run", "--depmap-snapshot", "bundle"]).depmap_snapshot.name == "bundle"


def test_snapshot_coverage_is_reported_descriptively(capsys) -> None:
    _report_dependency_coverage({
        "AVAILABLE": SimpleNamespace(
            profile_available=True,
            coverage_status="complete",
        ),
        "UNAVAILABLE": SimpleNamespace(
            profile_available=False,
            coverage_status="not_available",
        ),
    })

    assert capsys.readouterr().out == (
        "DepMap research-preview coverage: 1/2 profiles available "
        "(complete=1, not_available=1)\n"
    )


def test_pipeline_relays_the_optional_snapshot_to_core(monkeypatch) -> None:
    captured = {}
    sentinel = object()

    def fake_run_core_pipeline(**kwargs):
        captured.update(kwargs)
        return sentinel

    monkeypatch.setattr(pipeline_module, "run_core_pipeline", fake_run_core_pipeline)

    assert pipeline_module.run_pipeline(depmap_snapshot_path="portable-bundle") is sentinel
    assert captured["depmap_snapshot_path"] == "portable-bundle"

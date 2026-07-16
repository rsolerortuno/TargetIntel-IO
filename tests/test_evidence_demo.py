"""Offline regression coverage for the fabricated evidence demonstration."""

from __future__ import annotations

import importlib.util
from pathlib import Path


def test_fabricated_evidence_demo_runs_offline(tmp_path: Path) -> None:
    path = Path("examples/evidence/build_mock_evidence_demo.py")
    spec = importlib.util.spec_from_file_location("mock_evidence_demo", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    store, markdown, html = module.build_demo(tmp_path / "demo")

    assert store.is_file()
    assert "fabricated mock data only" in markdown.read_text(encoding="utf-8")
    assert "Fabricated evidence report" in html.read_text(encoding="utf-8")

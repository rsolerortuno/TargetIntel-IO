"""Release-level checks for the offline v0.4.0 feasibility demonstration."""
import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "examples" / "feasibility" / "run_v040_mock_demo.py"
spec = importlib.util.spec_from_file_location("v040_demo", SCRIPT)
demo = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(demo)


def test_demo_is_offline_and_retains_terminal_outcomes(tmp_path):
    summary = demo.run_demo(tmp_path)
    assert summary["offline"] and summary["no_live_transport"] and summary["no_llm"]
    assert {"TAP1", "IFNGR1", "STAT1"} <= set(summary["directed_requested_targets"])
    assert not ({"TAP1", "IFNGR1", "STAT1"} & set(summary["ranked_target_identifiers"]))
    assert {"TAP1", "IFNGR1", "STAT1"} <= set(summary["absent_from_ranked_recovered_by_directed"])
    assert summary["unresolved_targets"] and summary["no_record_targets"] and summary["failed_targets"]
    assert summary["coverage_numerator"] == 3 and summary["coverage_denominator"] == 6
    assert not summary["coverage_is_scientific_confidence"]
    assert summary["protected_outputs_unchanged"]


def test_demo_is_deterministic_and_reordered_universe_has_same_identity(tmp_path):
    one, two = demo.run_demo(tmp_path / "one"), demo.run_demo(tmp_path / "two")
    for key in ("target_universe_hash", "fetch_result_id", "coverage_id", "profile_ids", "modality_annotation_ids", "presentation_section_ids"):
        assert one[key] == two[key]
    from targetintel.feasibility import OpenTargetsFetchRequest
    assert OpenTargetsFetchRequest(query_type="directed_target_universe", target_universe=["TAP1", "IFNGR1", "STAT1"]).target_universe_hash == OpenTargetsFetchRequest(query_type="directed_target_universe", target_universe=["STAT1", "TAP1", "IFNGR1"]).target_universe_hash
    assert (tmp_path / "one" / "demo_summary.json").read_bytes() == (tmp_path / "two" / "demo_summary.json").read_bytes()
    manifest = json.loads((tmp_path / "one" / "demo_manifest.json").read_text())
    assert manifest["output_content_hashes"]["cards/TAP1.md"] == hashlib.sha256((tmp_path / "one" / "cards" / "TAP1.md").read_bytes()).hexdigest()


def test_cli_requires_explicit_output_dir():
    with pytest.raises(SystemExit):
        import sys
        old = sys.argv
        try:
            sys.argv = [str(SCRIPT)]
            demo.main()
        finally:
            sys.argv = old


def test_documentation_and_rendered_safety_restraint(tmp_path):
    demo.run_demo(tmp_path)
    markdown = (tmp_path / "cards" / "TAP1.md").read_text().lower().split("## target feasibility", 1)[1]
    html = (tmp_path / "reports" / "TAP1.html").read_text().lower().split("target feasibility", 1)[1]
    assert "research-only" in markdown and "recommended modality" not in markdown and "go/no-go" in markdown
    assert "the target is safe" not in markdown
    assert len((ROOT / "README.md").read_text().splitlines()) <= 360
    assert (ROOT / "docs" / "releases" / "v0.4.0.md").exists()
    assert (ROOT / "examples" / "feasibility" / "README.md").exists()

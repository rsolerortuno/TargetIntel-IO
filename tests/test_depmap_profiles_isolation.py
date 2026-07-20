"""Issue 503 must stay isolated from the deterministic prioritization path."""
from pathlib import Path


def test_profile_surface_has_no_pipeline_or_remote_dependencies() -> None:
    source = (Path(__file__).parents[1] / "targetintel" / "functional_dependency" / "depmap_profiles.py").read_text(encoding="utf-8")
    for forbidden in ("targetintel.scoring", "targetintel.intent_ranking", "targetintel.role_classifier", "targetintel.feature_table", "targetintel.modality", "targetintel.opentargets", "targetintel.llm", "requests", "urllib.request", "subprocess", "importlib", "eval("):
        assert forbidden not in source

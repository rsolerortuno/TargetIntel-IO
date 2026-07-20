from pathlib import Path

def test_universe_module_does_not_import_forbidden_execution_surfaces() -> None:
    text = (Path(__file__).parents[1] / "targetintel" / "functional_dependency" / "target_universes.py").read_text()
    for forbidden in ("import requests", "import subprocess", "eval(", "import importlib"):
        assert forbidden not in text

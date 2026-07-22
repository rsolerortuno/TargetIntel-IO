from __future__ import annotations

from pathlib import Path
import re


def test_publication_script_contains_complete_discovery_overlay_contract() -> None:
    source = Path("scripts/13_publish_depmap_v050.py").read_text()
    for text in ("Complete 331-identity discovery universe", "Strongest upward rank movements", "Strongest downward rank movements", "Research-preview DepMap overlay rank", "not biological validation"):
        assert text in source


def test_publication_script_does_not_label_real_reports_as_synthetic_fixtures() -> None:
    source = Path("scripts/13_publish_depmap_v050.py").read_text()
    assert "Descriptive real-release aggregate evidence only" in source
    assert "_real_release_markdown(item)" in source


def test_published_main_index_target_links_resolve_to_target_reports() -> None:
    """The outer published index must link into its targets/ subdirectory."""
    report_root = Path("examples/html_reports/depmap_26q1")
    index_html = (report_root / "index.html").read_text(encoding="utf-8")
    hrefs = re.findall(r'href="([^"]+\.html)"', index_html)
    target_hrefs = [href for href in hrefs if href.startswith("targets/")]

    assert target_hrefs
    assert all((report_root / href).is_file() for href in target_hrefs)

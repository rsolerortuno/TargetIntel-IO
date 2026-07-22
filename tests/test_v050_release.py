from __future__ import annotations

from pathlib import Path
import tomllib


def test_v050_release_documents_the_real_portable_bundle() -> None:
    assert tomllib.loads(Path("pyproject.toml").read_text())["project"]["version"] == "0.5.0"
    assert "Single-cell and spatial evidence integration is planned for v0.6.0." in Path("README.md").read_text()
    assert Path("data/releases/depmap/DepMap_Public_26Q1/source_manifest.json").is_file()
    assert "repository-safe aggregate evidence bundle is published" in Path("docs/releases/v0.5.0.md").read_text()


def test_real_publication_uses_real_source_urls_and_truthful_baseline_rendering() -> None:
    source_manifest = Path("data/releases/depmap/DepMap_Public_26Q1/source_manifest.json").read_text()
    braf_markdown = Path("examples/target_cards/depmap_26q1/BRAF.md").read_text()
    braf_html = Path("examples/html_reports/depmap_26q1/targets/BRAF.html").read_text()
    index_html = Path("examples/html_reports/depmap_26q1/index.html").read_text()
    assert "https://depmap.org/portal/data_page/?release=DepMap+Public+26Q1" in source_manifest
    assert "https://forum.depmap.org/t/announcing-the-26q1-release/4606" in source_manifest
    assert "| Antibody / IO-combination | 0.269 | 7 |" in braf_markdown
    assert "| Resistance biomarker | 0.482 | 11 |" in braf_markdown
    assert "| Tumor-intrinsic / small molecule | 0.845 | 1 |" in braf_markdown
    assert "0.269" in braf_html
    assert "0.482" in braf_html
    assert "0.845" in braf_html
    assert "Top antibody / IO-combination targets" in index_html
    assert "Top resistance biomarker candidates" in index_html
    assert "Top tumor-intrinsic / small-molecule candidates" in index_html
    assert "Authoritative baseline is retained; the full score table is not reproduced" not in index_html
    assert "Descriptive synthetic-fixture evidence only" not in braf_markdown
    assert "Descriptive synthetic-fixture evidence only" not in braf_html

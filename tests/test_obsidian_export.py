"""Offline plan and filesystem coverage for deterministic Obsidian export."""
from __future__ import annotations

from dataclasses import FrozenInstanceError
from hashlib import sha256
from pathlib import Path

import pytest

from targetintel.export import build_obsidian_export_plan, persist_obsidian_export
from targetintel.export.obsidian_models import ObsidianExportRequest
from targetintel.llm.contracts import canonical_json
from targetintel.llm.synthesis_models import (GROUNDED_STATEMENT_FORMAT_VERSION, GROUNDED_SYNTHESIS_FORMAT_VERSION,
    GroundedSynthesisStatement, GroundedTargetSynthesis)


def _digest(value): return sha256(canonical_json(value).encode()).hexdigest()


def _synthesis():
    statement_payload = {"statement_format_version": GROUNDED_STATEMENT_FORMAT_VERSION, "local_statement_key": "s1",
        "section_identifier": "contradictory_evidence", "statement_text": "The reviewed evidence reports no significant difference.",
        "evidence_item_ids": ["ev-1"], "evidence_payload_hashes": ["hash-1"], "support_relation": "contradicted",
        "uncertainty_level": "high_uncertainty", "limitation_text": "Observations conflict.", "safety_codes": [], "research_only": True}
    statement = GroundedSynthesisStatement(statement_id=_digest(statement_payload), **statement_payload)
    fields = {"synthesis_format_version": GROUNDED_SYNTHESIS_FORMAT_VERSION, "request_id": "request-1", "snapshot_id": "snapshot-1",
        "snapshot_manifest_hash": "manifest-1", "inventory_id": "inventory-1", "prompt_id": "prompt-1", "llm_response_id": "response-1",
        "target_identity": "B2M", "context": "melanoma", "synthesis_purpose": "target_evidence_summary",
        "sections": ("contradictory_evidence", "limitations", "uncertainties"),
        "evidence_coverage": ({"evidence_item_id": "ev-1", "disposition": "cited"},), "research_only": True}
    identity = {"synthesis_format_version": GROUNDED_SYNTHESIS_FORMAT_VERSION, "request_id": "request-1", "snapshot_id": "snapshot-1",
        "snapshot_manifest_hash": "manifest-1", "inventory_id": "inventory-1", "prompt_id": "prompt-1", "llm_response_id": "response-1",
        "target_identity": "B2M", "context": "melanoma", "synthesis_purpose": "target_evidence_summary",
        "sections": list(fields["sections"]), "statement_ids": [statement.statement_id], "evidence_coverage": list(fields["evidence_coverage"]), "research_only": True}
    return GroundedTargetSynthesis(synthesis_id=_digest(identity), llm_request_id="llm-request-1", provider_name="mock", model_name="mock",
        model_version=None, statements=(statement,), selected_item_count=1, cited_item_count=1, unsynthesized_item_count=0,
        non_clinical_use=True, no_score_or_ranking_generated=True, no_file_written=True, **fields)


def _request(vault: Path, synthesis, **changes):
    values = {"synthesis_id": synthesis.synthesis_id, "vault_root": str(vault), "relative_note_path": "notes/B2M.md",
              "requesting_actor_id": "researcher", "collision_policy": "idempotent_same_content", "frontmatter_version": "1.0.0",
              "renderer_version": "issue-309", "tags": ["research", "melanoma"]}
    values.update(changes)
    return ObsidianExportRequest.create(**values)


def test_plan_reuses_renderer_and_is_immutable_deterministic(tmp_path):
    synthesis = _synthesis(); request = _request(tmp_path, synthesis)
    plan = build_obsidian_export_plan(request, synthesis)
    assert plan == build_obsidian_export_plan(request, synthesis)
    assert plan.content_sha256 == sha256(plan.planned_note_bytes).hexdigest()
    assert plan.frontmatter.index("synthesis_id:") < plan.frontmatter.index("target:")
    for text in ("[evidence:ev-1]", "Observations conflict.", "high_uncertainty", "Research-only", "Non-clinical use", "No score or ranking was generated"):
        assert text in plan.markdown_body
    expected = Path("tests/fixtures/export/obsidian_expected_note.md").read_bytes()
    fixture_request = _request(Path("/tmp/obsidian-fixture-vault"), synthesis, requesting_actor_id="fixture")
    assert build_obsidian_export_plan(fixture_request, synthesis).planned_note_bytes == expected
    with pytest.raises(FrozenInstanceError):
        plan.plan_id = "changed"


def test_atomic_write_idempotency_and_collision(tmp_path):
    synthesis = _synthesis(); request = _request(tmp_path, synthesis); plan = build_obsidian_export_plan(request, synthesis)
    first = persist_obsidian_export(request, plan)
    destination = tmp_path / "notes" / "B2M.md"
    assert first.status == "written" and first.write_performed and destination.read_bytes() == plan.planned_note_bytes
    second = persist_obsidian_export(request, plan)
    assert second.status == "already_current" and not second.write_performed
    assert second.receipt_id == persist_obsidian_export(request, plan).receipt_id
    with pytest.raises(FrozenInstanceError):
        first.status = "collision"
    destination.write_bytes(b"user content")
    collision = persist_obsidian_export(request, plan)
    assert collision.status == "collision" and not collision.write_performed and destination.read_bytes() == b"user content"
    assert persist_obsidian_export(_request(tmp_path, synthesis, collision_policy="fail_if_exists"), plan).status == "identity_mismatch"


def test_path_and_vault_fail_closed(tmp_path):
    synthesis = _synthesis()
    missing = tmp_path / "missing"; request = _request(missing, synthesis); plan = build_obsidian_export_plan(request, synthesis)
    assert persist_obsidian_export(request, plan).status == "vault_not_found"
    file_root = tmp_path / "file"; file_root.write_text("x")
    request = _request(file_root, synthesis); plan = build_obsidian_export_plan(request, synthesis)
    assert persist_obsidian_export(request, plan).status == "vault_not_directory"
    vault = tmp_path / "vault"; vault.mkdir(); outside = tmp_path / "outside"; outside.mkdir()
    (vault / "notes").symlink_to(outside, target_is_directory=True)
    request = _request(vault, synthesis); plan = build_obsidian_export_plan(request, synthesis)
    assert persist_obsidian_export(request, plan).status == "symlink_escape"

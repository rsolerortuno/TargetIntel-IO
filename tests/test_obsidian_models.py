"""Offline immutable-contract coverage for deterministic Obsidian export."""
from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import datetime, timezone

import pytest

from targetintel.export.obsidian_models import ObsidianExportRequest


def _request(**changes):
    values = {"synthesis_id": "synthesis-1", "vault_root": "/tmp/explicit-vault", "relative_note_path": "research/B2M.md",
              "requesting_actor_id": "researcher", "collision_policy": "idempotent_same_content",
              "frontmatter_version": "1.0.0", "renderer_version": "issue-309", "tags": ["melanoma", "research"]}
    values.update(changes)
    return ObsidianExportRequest.create(**values)


def test_request_is_immutable_deterministic_and_excludes_operational_values():
    first = _request()
    second = _request(vault_root="/different/vault", requested_at=datetime(2026, 1, 1, tzinfo=timezone.utc), tags=["research", "melanoma"])
    assert first.request_id == second.request_id
    assert first.tags == ("melanoma", "research")
    assert first.canonical_json() == ObsidianExportRequest.from_dict(first.to_dict()).canonical_json()
    with pytest.raises(FrozenInstanceError):
        first.synthesis_id = "changed"


@pytest.mark.parametrize("changes", [
    {"requesting_actor_id": ""}, {"relative_note_path": "/absolute.md"}, {"relative_note_path": "../escape.md"},
    {"relative_note_path": "a/../escape.md"}, {"relative_note_path": "a\x00.md"}, {"relative_note_path": "missing-extension"},
    {"vault_root": "relative-vault"}, {"collision_policy": "overwrite"}, {"tags": ["same", "same"]}, {"credential": "no"}, {"nested": {"reasoning": "no"}},
])
def test_request_rejects_unsafe_or_unknown_inputs(changes):
    with pytest.raises(ValueError):
        _request(**changes)


def test_request_from_dict_rejects_unknown_fields():
    with pytest.raises(ValueError):
        ObsidianExportRequest.from_dict(_request().to_dict() | {"unexpected": "x"})

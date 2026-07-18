"""Pure plan construction and explicit, path-safe Obsidian persistence."""
from __future__ import annotations

import os
import tempfile
import json
from hashlib import sha256
from pathlib import Path
from typing import Any

from targetintel.llm.grounded_writer import render_grounded_synthesis_markdown
from targetintel.llm.contracts import canonical_json
from targetintel.llm.synthesis_models import GroundedTargetSynthesis, GroundedTargetSynthesisResult

from .obsidian_models import (FRONTMATTER_SCHEMA, OBSIDIAN_EXPORT_PLAN_FORMAT_VERSION,
    ObsidianExportPlan, ObsidianExportReceipt, ObsidianExportRequest, make_receipt)


def _yaml_scalar(value: str) -> str:
    """JSON string quoting is a deterministic YAML double-quoted scalar subset."""
    return json.dumps(value, ensure_ascii=False)


def _frontmatter(request: ObsidianExportRequest, synthesis: GroundedTargetSynthesis) -> str:
    fields: list[tuple[str, Any]] = [
        ("targetintel_schema", FRONTMATTER_SCHEMA), ("targetintel_schema_version", request.frontmatter_version),
        ("synthesis_id", synthesis.synthesis_id), ("request_id", request.request_id),
        ("snapshot_id", synthesis.snapshot_id), ("snapshot_manifest_hash", synthesis.snapshot_manifest_hash),
        ("inventory_id", synthesis.inventory_id), ("target", synthesis.target_identity),
    ]
    if synthesis.context is not None:
        fields.append(("context", synthesis.context))
    fields.extend([
        ("synthesis_purpose", synthesis.synthesis_purpose), ("selected_evidence_count", synthesis.selected_item_count),
        ("cited_evidence_count", synthesis.cited_item_count), ("unsynthesized_evidence_count", synthesis.unsynthesized_item_count),
        ("research_only", True), ("non_clinical_use", True), ("score_generated", False),
        ("ranking_generated", False),
    ])
    lines = ["---"]
    for key, value in fields:
        lines.append(f"{key}: {str(value).lower() if isinstance(value, bool) else value if isinstance(value, int) else _yaml_scalar(value)}")
    if request.tags:
        lines.append("tags:")
        lines.extend(f"  - {_yaml_scalar(tag)}" for tag in request.tags)
    else:
        lines.append("tags: []")
    return "\n".join(lines) + "\n---\n\n"


def build_obsidian_export_plan(request: ObsidianExportRequest, synthesis: GroundedTargetSynthesis) -> ObsidianExportPlan:
    if not isinstance(request, ObsidianExportRequest):
        raise TypeError("request must be ObsidianExportRequest")
    if not isinstance(synthesis, GroundedTargetSynthesis):
        raise TypeError("synthesis must be GroundedTargetSynthesis")
    if request.synthesis_id != synthesis.synthesis_id:
        raise ValueError("request and synthesis identity mismatch")
    frontmatter = _frontmatter(request, synthesis)
    body = render_grounded_synthesis_markdown(synthesis)
    unsynthesized = [record for record in synthesis.evidence_coverage if record.get("disposition") == "unsynthesized"]
    if unsynthesized:
        body += "\n## Unsynthesized Evidence Records\n\n"
        for record in unsynthesized:
            reason = record.get("reason", "not_recorded")
            body += f"- [evidence:{record['evidence_item_id']}] (reason: {reason})\n"
    note = (frontmatter + body).encode("utf-8")
    digest = sha256(note).hexdigest()
    payload = {"plan_format_version": OBSIDIAN_EXPORT_PLAN_FORMAT_VERSION, "export_request_id": request.request_id,
               "synthesis_id": synthesis.synthesis_id, "relative_destination_path": request.relative_note_path,
               "frontmatter": frontmatter, "markdown_body": body, "content_sha256": digest,
               "collision_policy": request.collision_policy, "research_only": True}
    plan_id = sha256(canonical_json(payload).encode("utf-8")).hexdigest()
    return ObsidianExportPlan(plan_format_version=OBSIDIAN_EXPORT_PLAN_FORMAT_VERSION, plan_id=plan_id,
        export_request_id=request.request_id, synthesis_id=synthesis.synthesis_id,
        relative_destination_path=request.relative_note_path, frontmatter=frontmatter, markdown_body=body,
        planned_note_bytes=note, content_sha256=digest, byte_count=len(note),
        collision_policy=request.collision_policy, research_only=True)


def synthesis_from_generated_result(result: GroundedTargetSynthesisResult) -> GroundedTargetSynthesis:
    if not isinstance(result, GroundedTargetSynthesisResult) or result.status != "generated" or result.synthesis is None:
        raise ValueError("a generated GroundedTargetSynthesisResult is required")
    return result.synthesis


def _receipt(status: str, request: Any, plan: Any, *codes: str, path: Path | None = None) -> ObsidianExportReceipt:
    return make_receipt(status=status, export_request_id=getattr(request, "request_id", None),
        export_plan_id=getattr(plan, "plan_id", None), synthesis_id=getattr(plan, "synthesis_id", getattr(request, "synthesis_id", None)),
        relative_destination_path=getattr(plan, "relative_destination_path", getattr(request, "relative_note_path", None)),
        content_sha256=getattr(plan, "content_sha256", None), byte_count=getattr(plan, "byte_count", None),
        collision_policy=getattr(plan, "collision_policy", getattr(request, "collision_policy", None)),
        write_performed=status == "written", error_codes=codes,
        operational_absolute_path=None if path is None else str(path))


def _destination(request: ObsidianExportRequest) -> tuple[str | None, Path | None, Path | None]:
    root = Path(request.vault_root)
    if not root.exists():
        return "vault_not_found", None, None
    if root.is_symlink():
        return "symlink_escape", None, None
    if not root.is_dir():
        return "vault_not_directory", None, None
    resolved_root = root.resolve(strict=True)
    current = resolved_root
    for component in request.relative_note_path.split("/")[:-1]:
        current = current / component
        if current.exists() and current.is_symlink():
            return "symlink_escape", None, None
        if current.exists() and not current.is_dir():
            return "unsafe_path", None, None
    destination = resolved_root.joinpath(*request.relative_note_path.split("/"))
    if destination.exists() and destination.is_symlink():
        return "symlink_escape", None, None
    try:
        destination.parent.resolve(strict=False).relative_to(resolved_root)
        destination.resolve(strict=False).relative_to(resolved_root)
    except ValueError:
        return "unsafe_path", None, None
    return None, resolved_root, destination


def persist_obsidian_export(request: ObsidianExportRequest, plan: ObsidianExportPlan) -> ObsidianExportReceipt:
    """Persist a precomputed plan; this function neither renders nor transforms science."""
    if not isinstance(request, ObsidianExportRequest):
        return _receipt("invalid_request", request, plan, "invalid_request")
    if not isinstance(plan, ObsidianExportPlan):
        return _receipt("invalid_plan", request, plan, "invalid_plan")
    try:
        # Re-run dataclass integrity checks to detect deliberate post-construction tampering.
        ObsidianExportPlan(**{name: getattr(plan, name) for name in plan.__dataclass_fields__})
    except (TypeError, ValueError, UnicodeError):
        return _receipt("invalid_plan", request, plan, "invalid_plan")
    if plan.export_request_id != request.request_id or plan.synthesis_id != request.synthesis_id or plan.relative_destination_path != request.relative_note_path or plan.collision_policy != request.collision_policy:
        return _receipt("identity_mismatch", request, plan, "request_plan_mismatch")
    status, root, destination = _destination(request)
    if status:
        return _receipt(status, request, plan, status)
    assert root is not None and destination is not None
    if destination.exists():
        try:
            existing = destination.read_bytes()
        except OSError:
            return _receipt("write_error", request, plan, "destination_read_failed", path=destination)
        if request.collision_policy == "idempotent_same_content" and existing == plan.planned_note_bytes:
            return _receipt("already_current", request, plan, path=destination)
        return _receipt("collision", request, plan, "destination_exists", path=destination)
    # Create only the requested path chain, checking each component after creation.
    parent = root
    try:
        for component in request.relative_note_path.split("/")[:-1]:
            parent = parent / component
            if not parent.exists():
                parent.mkdir()
            if parent.is_symlink():
                return _receipt("symlink_escape", request, plan, "symlink_escape")
            if not parent.is_dir():
                return _receipt("unsafe_path", request, plan, "unsafe_path")
            try:
                parent.resolve(strict=True).relative_to(root)
            except ValueError:
                return _receipt("symlink_escape", request, plan, "symlink_escape")
        # A hard link publishes complete bytes without replacing a concurrently-created user file.
        fd, temporary = tempfile.mkstemp(prefix=".targetintel-", suffix=".tmp", dir=parent)
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(plan.planned_note_bytes)
                handle.flush()
                os.fsync(handle.fileno())
            if destination.exists() or destination.is_symlink():
                return _receipt("collision" if not destination.is_symlink() else "symlink_escape", request, plan, "destination_exists")
            try:
                os.link(temporary, destination)
            except FileExistsError:
                return _receipt("collision", request, plan, "destination_exists", path=destination)
            return _receipt("written", request, plan, path=destination)
        finally:
            try:
                os.unlink(temporary)
            except FileNotFoundError:
                pass
    except OSError:
        return _receipt("write_error", request, plan, "atomic_write_failed", path=destination)

"""Immutable, deterministic contracts for explicit Obsidian export."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import PurePath
from typing import Any, Mapping

from targetintel.llm.contracts import canonical_json

OBSIDIAN_EXPORT_REQUEST_SCHEMA_ID = "targetintel.obsidian_export_request"
OBSIDIAN_EXPORT_REQUEST_SCHEMA_VERSION = "1.0.0"
OBSIDIAN_EXPORT_PLAN_FORMAT_VERSION = "targetintel.obsidian_export_plan.v1"
OBSIDIAN_EXPORT_RECEIPT_FORMAT_VERSION = "targetintel.obsidian_export_receipt.v1"
FRONTMATTER_SCHEMA = "targetintel.obsidian_grounded_synthesis"
COLLISION_POLICIES = frozenset({"fail_if_exists", "idempotent_same_content"})
RECEIPT_STATUSES = frozenset({"written", "already_current", "invalid_request", "invalid_synthesis", "invalid_plan", "identity_mismatch", "unsafe_path", "symlink_escape", "vault_not_found", "vault_not_directory", "collision", "write_error"})
_UNSAFE = ("secret", "password", "credential", "api_key", "apikey", "token", "authorization", "thinking", "reasoning", "chain_of_thought", "scratchpad", "analysis")


def _digest(value: Any) -> str:
    return sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _required(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return value


def _unsafe(value: Any) -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            key_text = str(key).casefold().replace("-", "_")
            if any(term in key_text for term in _UNSAFE):
                raise ValueError("unsafe export field")
            _unsafe(item)
    elif isinstance(value, (tuple, list)):
        for item in value:
            _unsafe(item)


def _utc(value: datetime | None, name: str) -> datetime | None:
    if value is None:
        return None
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")
    return value.astimezone(timezone.utc)


def _note_path(value: Any) -> str:
    value = _required(value, "relative_note_path")
    if "\x00" in value or value.startswith(("/", "\\")) or PurePath(value).is_absolute():
        raise ValueError("relative_note_path must be a safe relative path")
    parts = value.replace("\\", "/").split("/")
    if any(part in ("", ".", "..") for part in parts) or not value.endswith(".md"):
        raise ValueError("relative_note_path must be a safe .md path")
    return "/".join(parts)


@dataclass(frozen=True)
class ObsidianExportRequest:
    request_schema_id: str
    request_schema_version: str
    request_id: str
    synthesis_id: str
    vault_root: str
    relative_note_path: str
    requesting_actor_id: str
    collision_policy: str
    frontmatter_version: str
    renderer_version: str
    tags: tuple[str, ...] = ()
    requested_at: datetime | None = None

    def __post_init__(self) -> None:
        if self.request_schema_id != OBSIDIAN_EXPORT_REQUEST_SCHEMA_ID or self.request_schema_version != OBSIDIAN_EXPORT_REQUEST_SCHEMA_VERSION:
            raise ValueError("unknown export request schema")
        for name in ("request_id", "synthesis_id", "vault_root", "requesting_actor_id", "frontmatter_version", "renderer_version"):
            _required(getattr(self, name), name)
        if "\x00" in self.vault_root or not PurePath(self.vault_root).is_absolute():
            raise ValueError("vault_root must be an explicit absolute path")
        object.__setattr__(self, "relative_note_path", _note_path(self.relative_note_path))
        tags = tuple(self.tags)
        if any(not isinstance(tag, str) or not tag.strip() for tag in tags) or len(set(tags)) != len(tags):
            raise ValueError("tags must be non-empty and unique")
        object.__setattr__(self, "tags", tuple(sorted(tags)))
        if self.collision_policy not in COLLISION_POLICIES:
            raise ValueError("unknown collision policy")
        object.__setattr__(self, "requested_at", _utc(self.requested_at, "requested_at"))
        if self.request_id != _digest(self.identity_payload()):
            raise ValueError("export request identity mismatch")

    def identity_payload(self) -> dict[str, Any]:
        return {"request_schema_id": self.request_schema_id, "request_schema_version": self.request_schema_version,
                "synthesis_id": self.synthesis_id, "relative_note_path": self.relative_note_path,
                "requesting_actor_id": self.requesting_actor_id, "collision_policy": self.collision_policy,
                "frontmatter_version": self.frontmatter_version, "renderer_version": self.renderer_version,
                "tags": list(self.tags)}

    def to_dict(self) -> dict[str, Any]:
        result = self.identity_payload() | {"request_id": self.request_id, "vault_root": self.vault_root}
        if self.requested_at:
            result["requested_at"] = self.requested_at.isoformat(timespec="microseconds").replace("+00:00", "Z")
        return result

    def canonical_json(self) -> str:
        return canonical_json(self.to_dict())

    @classmethod
    def create(cls, **values: Any) -> "ObsidianExportRequest":
        values = dict(values)
        _unsafe(values)
        allowed = set(cls.__dataclass_fields__) - {"request_id"}
        if set(values) - allowed:
            raise ValueError("unknown export request fields")
        values.setdefault("request_schema_id", OBSIDIAN_EXPORT_REQUEST_SCHEMA_ID)
        values.setdefault("request_schema_version", OBSIDIAN_EXPORT_REQUEST_SCHEMA_VERSION)
        values["relative_note_path"] = _note_path(values.get("relative_note_path"))
        tags = values.get("tags", ())
        if not isinstance(tags, (tuple, list)) or len(set(tags)) != len(tags):
            raise ValueError("invalid tags")
        values["tags"] = tuple(sorted(tags))
        payload = {key: values.get(key) for key in ("request_schema_id", "request_schema_version", "synthesis_id", "relative_note_path", "requesting_actor_id", "collision_policy", "frontmatter_version", "renderer_version", "tags")}
        payload["tags"] = list(values["tags"])
        values["request_id"] = _digest(payload)
        return cls(**values)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ObsidianExportRequest":
        allowed = set(cls.__dataclass_fields__)
        required = allowed - {"tags", "requested_at"}
        if not isinstance(data, Mapping) or set(data) - allowed or required - set(data):
            raise ValueError("invalid export request fields")
        _unsafe(data)
        values = dict(data)
        if isinstance(values.get("requested_at"), str):
            values["requested_at"] = datetime.fromisoformat(values["requested_at"].replace("Z", "+00:00"))
        return cls(**values)


@dataclass(frozen=True)
class ObsidianExportPlan:
    plan_format_version: str
    plan_id: str
    export_request_id: str
    synthesis_id: str
    relative_destination_path: str
    frontmatter: str
    markdown_body: str
    planned_note_bytes: bytes
    content_sha256: str
    byte_count: int
    collision_policy: str
    research_only: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(self, "relative_destination_path", _note_path(self.relative_destination_path))
        object.__setattr__(self, "planned_note_bytes", bytes(self.planned_note_bytes))
        if self.plan_format_version != OBSIDIAN_EXPORT_PLAN_FORMAT_VERSION or self.collision_policy not in COLLISION_POLICIES or not self.research_only:
            raise ValueError("invalid export plan")
        if self.planned_note_bytes != (self.frontmatter + self.markdown_body).encode("utf-8") or self.byte_count != len(self.planned_note_bytes) or self.content_sha256 != sha256(self.planned_note_bytes).hexdigest():
            raise ValueError("invalid planned note bytes")
        if self.plan_id != _digest(self.identity_payload()):
            raise ValueError("export plan identity mismatch")

    def identity_payload(self) -> dict[str, Any]:
        return {"plan_format_version": self.plan_format_version, "export_request_id": self.export_request_id,
                "synthesis_id": self.synthesis_id, "relative_destination_path": self.relative_destination_path,
                "frontmatter": self.frontmatter, "markdown_body": self.markdown_body,
                "content_sha256": self.content_sha256, "collision_policy": self.collision_policy,
                "research_only": self.research_only}

    def to_dict(self) -> dict[str, Any]:
        return self.identity_payload() | {"plan_id": self.plan_id, "planned_note_utf8": self.planned_note_bytes.decode("utf-8"), "byte_count": self.byte_count}

    def canonical_json(self) -> str:
        return canonical_json(self.to_dict())


@dataclass(frozen=True)
class ObsidianExportReceipt:
    receipt_format_version: str
    receipt_id: str
    status: str
    export_request_id: str | None
    export_plan_id: str | None
    synthesis_id: str | None
    relative_destination_path: str | None
    content_sha256: str | None
    byte_count: int | None
    collision_policy: str | None
    write_performed: bool
    error_codes: tuple[str, ...] = ()
    operational_absolute_path: str | None = None
    completed_at: datetime | None = None

    def __post_init__(self) -> None:
        if self.status not in RECEIPT_STATUSES or (self.status == "written") != self.write_performed:
            raise ValueError("invalid export receipt")
        object.__setattr__(self, "error_codes", tuple(sorted(set(self.error_codes))))
        if any(not isinstance(code, str) or not code or "\n" in code or "traceback" in code.casefold() for code in self.error_codes):
            raise ValueError("invalid receipt error codes")
        object.__setattr__(self, "completed_at", _utc(self.completed_at, "completed_at"))
        if self.receipt_format_version != OBSIDIAN_EXPORT_RECEIPT_FORMAT_VERSION or self.receipt_id != _digest(self.identity_payload()):
            raise ValueError("export receipt identity mismatch")

    def identity_payload(self) -> dict[str, Any]:
        return {"receipt_format_version": self.receipt_format_version, "status": self.status,
                "export_request_id": self.export_request_id, "export_plan_id": self.export_plan_id,
                "synthesis_id": self.synthesis_id, "relative_destination_path": self.relative_destination_path,
                "content_sha256": self.content_sha256, "byte_count": self.byte_count,
                "collision_policy": self.collision_policy, "write_performed": self.write_performed,
                "error_codes": list(self.error_codes)}

    def to_dict(self) -> dict[str, Any]:
        result = self.identity_payload() | {"receipt_id": self.receipt_id}
        if self.operational_absolute_path is not None:
            result["operational_absolute_path"] = self.operational_absolute_path
        if self.completed_at:
            result["completed_at"] = self.completed_at.isoformat(timespec="microseconds").replace("+00:00", "Z")
        return result

    def canonical_json(self) -> str:
        return canonical_json(self.to_dict())


def make_receipt(**values: Any) -> ObsidianExportReceipt:
    values.setdefault("receipt_format_version", OBSIDIAN_EXPORT_RECEIPT_FORMAT_VERSION)
    values.setdefault("error_codes", ())
    values["error_codes"] = tuple(sorted(set(values["error_codes"])))
    payload = {key: values.get(key) for key in ("receipt_format_version", "status", "export_request_id", "export_plan_id", "synthesis_id", "relative_destination_path", "content_sha256", "byte_count", "collision_policy", "write_performed")}
    payload["error_codes"] = list(values["error_codes"])
    return ObsidianExportReceipt(receipt_id=_digest(payload), **values)

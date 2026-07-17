"""Safe JSON request loading and auditable LLM run artifact handling."""

from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import tempfile
from typing import Any, Mapping

from .contracts import LLMRequest, LLMResponse, canonical_json
from .execution import ExecutionResult
from .providers.mock import MockOutcome


ARTIFACT_FORMAT_VERSION = "targetintel-llm-run-v1"
_REQUEST_FIELDS = frozenset(LLMRequest.__dataclass_fields__)
_OUTCOME_FIELDS = frozenset({"status", "raw_text", "structured_output", "finish_reason", "token_usage", "latency_ms", "error_category", "error_message"})


class RequestDocumentError(ValueError):
    pass


class ArtifactError(ValueError):
    pass


def _read_json_with_raw(path: Path, label: str) -> tuple[Any, bytes]:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise RequestDocumentError(f"could not read {label}") from exc
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise RequestDocumentError(f"{label} is not valid UTF-8") from exc
    try:
        return json.loads(text), raw
    except json.JSONDecodeError as exc:
        raise RequestDocumentError(f"{label} is not valid JSON") from exc


def _read_json(path: Path, label: str) -> Any:
    return _read_json_with_raw(path, label)[0]


def load_request(path: str | Path) -> tuple[LLMRequest, str]:
    """Load one explicit request document; no environment or retrieval is consulted."""
    document_path = Path(path)
    document, raw = _read_json_with_raw(document_path, "request document")
    if not isinstance(document, Mapping):
        raise RequestDocumentError("request document must be a top-level object")
    unknown = set(document).difference(_REQUEST_FIELDS)
    if unknown:
        raise RequestDocumentError("unknown request field: " + sorted(map(str, unknown))[0])
    if document.get("source_text") is not None and document.get("structured_source_content") is not None:
        raise RequestDocumentError("source_text and structured_source_content cannot both be supplied")
    try:
        request = LLMRequest.from_dict(document)
    except (TypeError, ValueError) as exc:
        raise RequestDocumentError(f"invalid request: {exc}") from exc
    return request, sha256(raw).hexdigest()


def load_mock_script(path: str | Path) -> Mapping[str, Mapping[str, Any]]:
    document = _read_json(Path(path), "mock script")
    if not isinstance(document, Mapping):
        raise RequestDocumentError("mock script must be a top-level object")
    cleaned: dict[str, Mapping[str, Any]] = {}
    for request_id, outcome in document.items():
        if not isinstance(request_id, str) or not request_id:
            raise RequestDocumentError("mock script request IDs must be non-empty strings")
        if not isinstance(outcome, Mapping):
            raise RequestDocumentError("mock script outcomes must be objects")
        unknown = set(outcome).difference(_OUTCOME_FIELDS)
        if unknown:
            raise RequestDocumentError("unknown mock outcome field: " + sorted(map(str, unknown))[0])
        try:
            MockOutcome.from_dict(outcome)
        except (KeyError, TypeError, ValueError) as exc:
            raise RequestDocumentError("invalid mock outcome") from exc
        cleaned[request_id] = dict(outcome)
    return cleaned


def _sha(data: bytes) -> str:
    return sha256(data).hexdigest()


def _atomic_write(path: Path, data: bytes) -> str:
    try:
        with tempfile.NamedTemporaryFile(mode="wb", dir=path.parent, prefix=".targetintel-", delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(data)
            handle.flush()
        temporary.replace(path)
    except OSError as exc:
        try:
            temporary.unlink(missing_ok=True)
        except UnboundLocalError:
            pass
        raise ArtifactError("could not write run artifact") from exc
    return _sha(data)


def write_run_artifacts(output_directory: str | Path, result: ExecutionResult, *, input_file_sha256: str, overwrite: bool = False) -> Path:
    """Write request, response, then a completion manifest in the requested directory."""
    output = Path(output_directory)
    if output.exists() and not output.is_dir():
        raise ArtifactError("output path is not a directory")
    if output.exists() and not overwrite:
        raise ArtifactError("output directory already exists; use --overwrite to replace run artifacts")
    try:
        output.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise ArtifactError("could not create output directory") from exc
    manifest_path = output / "manifest.json"
    if overwrite:
        try:
            manifest_path.unlink(missing_ok=True)
        except OSError as exc:
            raise ArtifactError("could not prepare output directory") from exc
    request_document = {
        "artifact_format_version": ARTIFACT_FORMAT_VERSION,
        "input_file_sha256": input_file_sha256,
        "request_identity": result.request.payload_identity(),
        "request": result.request.to_dict(),
    }
    response_document = {
        "artifact_format_version": ARTIFACT_FORMAT_VERSION,
        "response_identity": result.response.payload_identity(),
        "response": result.response.to_dict(),
        "operational": {
            "executed": result.executed,
            "started_at": result.started_at.isoformat().replace("+00:00", "Z"),
            "finished_at": result.finished_at.isoformat().replace("+00:00", "Z"),
        },
    }
    request_bytes = canonical_json(request_document).encode("utf-8")
    response_bytes = canonical_json(response_document).encode("utf-8")
    hashes = {
        "request.json": _atomic_write(output / "request.json", request_bytes),
        "response.json": _atomic_write(output / "response.json", response_bytes),
    }
    manifest = {
        "artifact_format_version": ARTIFACT_FORMAT_VERSION,
        "completion_state": "complete",
        "request_identity": result.request.payload_identity(),
        "response_identity": result.response.payload_identity(),
        "provider_name": result.response.provider_name,
        "model_name": result.response.model_name,
        "response_status": result.response.status.value,
        "artifact_sha256": hashes,
        "operational": {"run_directory": str(output), "executed": result.executed},
    }
    _atomic_write(manifest_path, canonical_json(manifest).encode("utf-8"))
    return output


def inspect_run(directory: str | Path) -> Mapping[str, Any]:
    root = Path(directory)
    manifest_path = root / "manifest.json"
    try:
        manifest = _read_json(manifest_path, "manifest")
    except RequestDocumentError as exc:
        raise ArtifactError(str(exc)) from exc
    if not isinstance(manifest, Mapping) or manifest.get("artifact_format_version") != ARTIFACT_FORMAT_VERSION:
        raise ArtifactError("unsupported or invalid artifact format")
    if manifest.get("completion_state") != "complete":
        raise ArtifactError("run is not complete")
    hashes = manifest.get("artifact_sha256")
    if not isinstance(hashes, Mapping):
        raise ArtifactError("manifest has no artifact hashes")
    documents: dict[str, Any] = {}
    for name in ("request.json", "response.json"):
        path = root / name
        try:
            raw = path.read_bytes()
        except OSError as exc:
            raise ArtifactError(f"missing required artifact: {name}") from exc
        if hashes.get(name) != _sha(raw):
            raise ArtifactError(f"artifact hash mismatch: {name}")
        try:
            documents[name] = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ArtifactError(f"invalid artifact: {name}") from exc
        if not isinstance(documents[name], Mapping) or documents[name].get("artifact_format_version") != ARTIFACT_FORMAT_VERSION:
            raise ArtifactError(f"incompatible artifact format: {name}")
    try:
        request = LLMRequest.from_dict(documents["request.json"]["request"])
        response = LLMResponse.from_dict(documents["response.json"]["response"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ArtifactError("artifact contract is invalid") from exc
    if request.payload_identity() != manifest.get("request_identity") or response.payload_identity() != manifest.get("response_identity"):
        raise ArtifactError("artifact identity mismatch")
    if (manifest.get("provider_name"), manifest.get("model_name"), manifest.get("response_status")) != (response.provider_name, response.model_name, response.status.value):
        raise ArtifactError("manifest response summary mismatch")
    return {"provider_name": manifest.get("provider_name"), "model_name": manifest.get("model_name"), "response_status": manifest.get("response_status"), "completion_state": manifest.get("completion_state"), "response": documents["response.json"].get("response")}

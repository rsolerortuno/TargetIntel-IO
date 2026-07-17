import json
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path

import pytest

import targetintel.llm.io as llm_io
from targetintel.llm.execution import execute_request, not_executed_result
from targetintel.llm.io import ArtifactError, RequestDocumentError, inspect_run, load_mock_script, load_request, write_run_artifacts
from targetintel.llm.providers import HTTPResponse, MockProvider, OllamaConfig, OllamaProvider


FIXTURES = Path(__file__).parent / "fixtures" / "llm"


def request_document(**changes):
    value = {
        "request_id": "request-success", "task_type": "grounded_extraction",
        "source_document_id": "doc-1", "prompt_id": "prompt", "prompt_version": "1",
        "system_instruction": "system", "user_instruction": "user",
        "response_schema_id": "schema", "response_schema_version": "1", "source_text": "exact source\ntext",
    }
    value.update(changes)
    return value


def write_request(tmp_path, value):
    path = tmp_path / "request.json"
    path.write_text(json.dumps(value), encoding="utf-8")
    return path


def test_loader_is_explicit_and_preserves_source(tmp_path):
    request, _ = load_request(write_request(tmp_path, request_document()))
    assert request.source_text == "exact source\ntext"
    assert request.payload_identity() == load_request(tmp_path / "request.json")[0].payload_identity()


def test_loader_hashes_the_parsed_bytes_without_rereading(tmp_path, monkeypatch):
    path = write_request(tmp_path, request_document())
    original_read_bytes = Path.read_bytes
    reads = 0

    def read_once(value):
        nonlocal reads
        if value == path:
            reads += 1
            if reads > 1:
                raise AssertionError("request document was read more than once")
        return original_read_bytes(value)

    monkeypatch.setattr(Path, "read_bytes", read_once)
    _, content_hash = load_request(path)

    assert reads == 1
    assert content_hash == sha256(original_read_bytes(path)).hexdigest()


def test_versioned_structured_fixture_is_canonical():
    request, _ = load_request(FIXTURES / "execution_request_structured.json")
    assert request.source_text is None
    assert request.structured_source_content["a"] == ("fixture", 1)
    script = load_mock_script(FIXTURES / "execution_mock_script.json")
    assert MockProvider(script).generate(request).status.value == "permanent_failure"


@pytest.mark.parametrize("contents,message", [(b"\xff", "UTF-8"), (b"{", "JSON"), (b"[]", "top-level object")])
def test_loader_rejects_invalid_documents(tmp_path, contents, message):
    path = tmp_path / "request.json"
    path.write_bytes(contents)
    with pytest.raises(RequestDocumentError, match=message):
        load_request(path)


def test_loader_rejects_unknown_conflicting_and_secret_content(tmp_path):
    with pytest.raises(RequestDocumentError, match="unknown"):
        load_request(write_request(tmp_path, request_document(extra=True)))
    with pytest.raises(RequestDocumentError, match="cannot both"):
        load_request(write_request(tmp_path, request_document(structured_source_content={"a": 1})))
    with pytest.raises(RequestDocumentError, match="secrets"):
        load_request(write_request(tmp_path, request_document(metadata={"secret": "no"})))


def test_mock_script_rejects_unknown_outcome_field(tmp_path):
    path = tmp_path / "script.json"
    path.write_text('{"r":{"status":"success","bad":true}}', encoding="utf-8")
    with pytest.raises(RequestDocumentError, match="unknown"):
        load_mock_script(path)


def test_mock_script_rejects_outcome_missing_required_status(tmp_path):
    path = tmp_path / "script.json"
    path.write_text('{"r":{"raw_text":"offline"}}', encoding="utf-8")
    with pytest.raises(RequestDocumentError, match="invalid mock outcome"):
        load_mock_script(path)


def test_execute_once_and_dry_run_never_calls_provider(tmp_path):
    request, content_hash = load_request(write_request(tmp_path, request_document()))
    provider = MockProvider({"request-success": {"status": "success", "raw_text": "ok"}})
    executed = execute_request(request, provider, clock=lambda: datetime(2025, 1, 1, tzinfo=timezone.utc))
    assert executed.executed and len(provider.call_history) == 1
    planned = not_executed_result(request, "mock", "mock-model", clock=lambda: datetime(2025, 1, 1, tzinfo=timezone.utc))
    assert not planned.executed and len(provider.call_history) == 1
    run = write_run_artifacts(tmp_path / "run", planned, input_file_sha256=content_hash)
    assert inspect_run(run)["response_status"] == "not_executed"


def test_execute_ollama_once_with_injected_fake_transport():
    """The execution service supports local Ollama without touching a socket."""
    class FakeTransport:
        def __init__(self):
            self.calls = []

        def send(self, method, url, body, headers, timeout):
            self.calls.append((method, url, body, dict(headers), timeout))
            return HTTPResponse(200, {}, b'{"model":"offline-model","message":{"role":"assistant","content":"offline"},"done":true}')

    transport = FakeTransport()
    request, _ = load_request(FIXTURES / "execution_request_text.json")
    provider = OllamaProvider(OllamaConfig("offline-model"), transport=transport)
    result = execute_request(request, provider)

    assert result.executed
    assert result.status.value == "success"
    assert len(transport.calls) == 1


def test_artifacts_record_hashes_and_detect_tampering(tmp_path):
    request, content_hash = load_request(write_request(tmp_path, request_document()))
    result = execute_request(request, MockProvider({"request-success": {"status": "success", "raw_text": "ok"}}))
    run = write_run_artifacts(tmp_path / "run", result, input_file_sha256=content_hash)
    manifest = json.loads((run / "manifest.json").read_text())
    assert manifest["artifact_format_version"] == "targetintel-llm-run-v1"
    assert set(manifest["artifact_sha256"]) == {"request.json", "response.json"}
    (run / "request.json").write_text("{}", encoding="utf-8")
    with pytest.raises(ArtifactError, match="hash mismatch"):
        inspect_run(run)


def test_existing_directory_fails_closed(tmp_path):
    request, content_hash = load_request(write_request(tmp_path, request_document()))
    result = not_executed_result(request, "mock", "mock-model")
    output = tmp_path / "run"
    output.mkdir()
    (output / "unrelated.txt").write_text("x")
    with pytest.raises(ArtifactError, match="already exists"):
        write_run_artifacts(output, result, input_file_sha256=content_hash)


def test_overwrite_replaces_completed_artifacts(tmp_path):
    request, content_hash = load_request(write_request(tmp_path, request_document()))
    first = execute_request(request, MockProvider({"request-success": {"status": "success", "raw_text": "first"}}))
    output = write_run_artifacts(tmp_path / "run", first, input_file_sha256=content_hash)
    second = execute_request(request, MockProvider({"request-success": {"status": "success", "raw_text": "second"}}))

    write_run_artifacts(output, second, input_file_sha256=content_hash, overwrite=True)

    assert inspect_run(output)["response"]["raw_text"] == "second"


def test_partial_write_never_creates_completion_manifest(tmp_path, monkeypatch):
    request, content_hash = load_request(write_request(tmp_path, request_document()))
    result = not_executed_result(request, "mock", "mock-model")
    original_write = llm_io._atomic_write

    def fail_response(path, data):
        if path.name == "response.json":
            raise ArtifactError("simulated write failure")
        return original_write(path, data)

    monkeypatch.setattr(llm_io, "_atomic_write", fail_response)
    output = tmp_path / "partial"
    with pytest.raises(ArtifactError, match="simulated"):
        write_run_artifacts(output, result, input_file_sha256=content_hash)
    assert not (output / "manifest.json").exists()


@pytest.mark.parametrize("artifact", ["response.json", "request.json"])
def test_inspect_run_detects_changed_artifacts(tmp_path, artifact):
    request, content_hash = load_request(write_request(tmp_path, request_document()))
    result = execute_request(request, MockProvider({"request-success": {"status": "success", "raw_text": "ok"}}))
    run = write_run_artifacts(tmp_path / "run", result, input_file_sha256=content_hash)
    (run / artifact).write_text("{}", encoding="utf-8")

    with pytest.raises(ArtifactError, match="hash mismatch"):
        inspect_run(run)


def test_inspect_run_detects_missing_artifact(tmp_path):
    request, content_hash = load_request(write_request(tmp_path, request_document()))
    result = not_executed_result(request, "mock", "mock-model")
    run = write_run_artifacts(tmp_path / "run", result, input_file_sha256=content_hash)
    (run / "response.json").unlink()

    with pytest.raises(ArtifactError, match="missing required artifact: response.json"):
        inspect_run(run)


def test_identities_exclude_operational_timestamps(tmp_path):
    request, content_hash = load_request(write_request(tmp_path, request_document()))
    provider = MockProvider({"request-success": {"status": "success", "raw_text": "ok"}})
    first = execute_request(request, provider, clock=lambda: datetime(2025, 1, 1, tzinfo=timezone.utc))
    second = execute_request(request, provider, clock=lambda: datetime(2025, 1, 2, tzinfo=timezone.utc))
    first_run = write_run_artifacts(tmp_path / "first", first, input_file_sha256=content_hash)
    second_run = write_run_artifacts(tmp_path / "second", second, input_file_sha256=content_hash)
    first_manifest = json.loads((first_run / "manifest.json").read_text(encoding="utf-8"))
    second_manifest = json.loads((second_run / "manifest.json").read_text(encoding="utf-8"))

    assert first_manifest["request_identity"] == second_manifest["request_identity"]
    assert first_manifest["response_identity"] == second_manifest["response_identity"]
    assert json.loads((first_run / "response.json").read_text())["operational"] != json.loads((second_run / "response.json").read_text())["operational"]

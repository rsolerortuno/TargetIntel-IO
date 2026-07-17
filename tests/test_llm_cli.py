import json

from targetintel.llm.cli import ExitCode, main


def request(path):
    path.write_text(json.dumps({
        "request_id": "request-success", "task_type": "grounded_extraction", "source_document_id": "doc",
        "prompt_id": "p", "prompt_version": "1", "system_instruction": "s", "user_instruction": "u",
        "response_schema_id": "schema", "response_schema_version": "1", "source_text": "private source text",
    }), encoding="utf-8")


def test_validate_request_avoids_source_stdout(tmp_path, capsys):
    path = tmp_path / "request.json"
    request(path)
    assert main(["validate-request", str(path)]) == ExitCode.SUCCESS
    assert "private source text" not in capsys.readouterr().out


def test_mock_execute_and_inspect(tmp_path):
    document, script, output = tmp_path / "request.json", tmp_path / "script.json", tmp_path / "run"
    request(document)
    script.write_text('{"request-success":{"status":"success","raw_text":"offline"}}', encoding="utf-8")
    assert main(["execute", str(document), "--provider", "mock", "--mock-script", str(script), "--output", str(output)]) == ExitCode.SUCCESS
    assert main(["inspect-run", str(output)]) == ExitCode.SUCCESS


def test_dry_run_and_ollama_gate(tmp_path):
    document = tmp_path / "request.json"
    request(document)
    assert main(["execute", str(document), "--provider", "ollama", "--model", "offline", "--dry-run", "--output", str(tmp_path / "dry")]) == ExitCode.SUCCESS
    assert main(["execute", str(document), "--provider", "ollama", "--model", "offline", "--output", str(tmp_path / "gated")]) == ExitCode.SUCCESS
    assert json.loads((tmp_path / "gated" / "response.json").read_text())["response"]["provenance"]["result_status"] == "not_executed"


def test_invalid_request_has_stable_exit_code(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text("[]", encoding="utf-8")
    assert main(["validate-request", str(path)]) == ExitCode.INVALID_REQUEST


def test_malformed_mock_script_has_invalid_request_exit_code(tmp_path):
    document, script = tmp_path / "request.json", tmp_path / "script.json"
    request(document)
    script.write_text('{"request-success":{"raw_text":"offline"}}', encoding="utf-8")
    assert main([
        "execute", str(document), "--provider", "mock", "--mock-script", str(script),
        "--output", str(tmp_path / "run"),
    ]) == ExitCode.INVALID_REQUEST


def test_provider_failures_have_stable_cli_exit_codes(tmp_path):
    outcomes = [
        ("retryable_failure", "connection_failure", ExitCode.RETRYABLE_FAILURE),
        ("permanent_failure", "permanent_provider_failure", ExitCode.PERMANENT_FAILURE),
        ("malformed_output", "malformed_provider_response", ExitCode.MALFORMED_OUTPUT),
    ]
    for status, category, expected in outcomes:
        document = tmp_path / f"{status}-request.json"
        script = tmp_path / f"{status}-script.json"
        request(document)
        script.write_text(json.dumps({
            "request-success": {
                "status": status,
                "error_category": category,
                "error_message": "sanitized fixture failure",
            },
        }), encoding="utf-8")
        assert main([
            "execute", str(document), "--provider", "mock", "--mock-script", str(script),
            "--output", str(tmp_path / f"{status}-run"),
        ]) == expected


def test_existing_output_has_stable_write_failure_exit_code(tmp_path):
    document, script, output = tmp_path / "request.json", tmp_path / "script.json", tmp_path / "run"
    request(document)
    script.write_text('{"request-success":{"status":"success","raw_text":"offline"}}', encoding="utf-8")
    arguments = ["execute", str(document), "--provider", "mock", "--mock-script", str(script), "--output", str(output)]
    assert main(arguments) == ExitCode.SUCCESS
    assert main(arguments) == ExitCode.OUTPUT_FAILURE

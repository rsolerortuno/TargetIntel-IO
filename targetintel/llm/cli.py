"""Command-line interface for auditable operational LLM runs."""

from __future__ import annotations

import argparse
from enum import IntEnum
import json
from pathlib import Path
from typing import Sequence
from urllib.parse import urlsplit

from .execution import execute_request, not_executed_result
from .io import ArtifactError, RequestDocumentError, inspect_run, load_mock_script, load_request, write_run_artifacts
from .contracts import LLMResultStatus
from .providers import MockProvider, OllamaConfig, OllamaProvider


class ExitCode(IntEnum):
    SUCCESS = 0
    USAGE = 2
    INVALID_REQUEST = 3
    INVALID_PROVIDER = 4
    RETRYABLE_FAILURE = 5
    PERMANENT_FAILURE = 6
    MALFORMED_OUTPUT = 7
    OUTPUT_FAILURE = 8
    INVALID_RUN = 9
    INTERNAL_FAILURE = 10


class ProviderConfigurationError(ValueError):
    pass


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m targetintel.llm")
    sub = parser.add_subparsers(dest="command", required=True)
    validate = sub.add_parser("validate-request")
    validate.add_argument("request_json")
    execute = sub.add_parser("execute")
    execute.add_argument("request_json")
    execute.add_argument("--provider", required=True, choices=("mock", "ollama"))
    execute.add_argument("--output", required=True)
    execute.add_argument("--model")
    execute.add_argument("--mock-script")
    execute.add_argument("--ollama-url", default="http://127.0.0.1:11434")
    execute.add_argument("--schema")
    execute.add_argument("--allow-local-network", action="store_true")
    execute.add_argument("--dry-run", action="store_true")
    execute.add_argument("--overwrite", action="store_true")
    inspect = sub.add_parser("inspect-run")
    inspect.add_argument("run_directory")
    inspect.add_argument("--show-response", action="store_true")
    return parser


def _local_url(url: str) -> bool:
    parsed = urlsplit(url)
    return parsed.hostname in {"127.0.0.1", "localhost", "::1"} and parsed.username is None and parsed.password is None


def _provider(args: argparse.Namespace):
    if args.provider == "mock":
        if not args.dry_run and not args.mock_script:
            raise ProviderConfigurationError("--mock-script is required for mock execution")
        script = load_mock_script(args.mock_script) if args.mock_script else {}
        return MockProvider(script, model_name=args.model or "mock-model"), args.model or "mock-model"
    if not args.model:
        raise ProviderConfigurationError("--model is required for ollama")
    if not _local_url(args.ollama_url):
        raise ProviderConfigurationError("--ollama-url must use a loopback host without credentials")
    schema_resolver = None
    if args.schema:
        try:
            schema = json.loads(Path(args.schema).read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ProviderConfigurationError("schema document is not valid UTF-8 JSON") from exc
        if not isinstance(schema, dict):
            raise ProviderConfigurationError("schema document must be an object")
        schema_resolver = lambda _schema_id, _schema_version: schema
    return OllamaProvider(OllamaConfig(args.model, base_url=args.ollama_url), schema_resolver=schema_resolver), args.model


def _response_exit(status: LLMResultStatus) -> ExitCode:
    if status is LLMResultStatus.SUCCESS or status is LLMResultStatus.NOT_EXECUTED:
        return ExitCode.SUCCESS
    if status in {LLMResultStatus.RETRYABLE_FAILURE, LLMResultStatus.TIMEOUT}:
        return ExitCode.RETRYABLE_FAILURE
    if status is LLMResultStatus.MALFORMED_OUTPUT:
        return ExitCode.MALFORMED_OUTPUT
    return ExitCode.PERMANENT_FAILURE


def main(argv: Sequence[str] | None = None) -> int:
    parser = _parser()
    try:
        try:
            args = parser.parse_args(argv)
        except SystemExit as exc:
            return int(exc.code)
        if args.command == "validate-request":
            request, _ = load_request(args.request_json)
            print(f"valid request: {request.request_id}")
            return int(ExitCode.SUCCESS)
        if args.command == "inspect-run":
            summary = inspect_run(args.run_directory)
            print(f"run complete: provider={summary['provider_name']} status={summary['response_status']}")
            if args.show_response:
                import json
                print(json.dumps(summary["response"], ensure_ascii=False, sort_keys=True))
            return int(ExitCode.SUCCESS)
        request, content_hash = load_request(args.request_json)
        provider, model = _provider(args)
        if args.dry_run:
            result = not_executed_result(request, args.provider, model, message="Dry run: provider generation was not invoked")
        elif args.provider == "ollama" and not args.allow_local_network:
            result = not_executed_result(request, "ollama", model, message="Ollama execution requires --allow-local-network")
        else:
            result = execute_request(request, provider)
        write_run_artifacts(args.output, result, input_file_sha256=content_hash, overwrite=args.overwrite)
        print(f"run written: status={result.status.value}")
        return int(_response_exit(result.status))
    except RequestDocumentError as exc:
        print(f"error: {exc}")
        return int(ExitCode.INVALID_REQUEST)
    except ProviderConfigurationError as exc:
        print(f"error: {exc}")
        return int(ExitCode.INVALID_PROVIDER)
    except ArtifactError as exc:
        print(f"error: {exc}")
        return int(ExitCode.OUTPUT_FAILURE if getattr(locals().get("args", None), "command", None) == "execute" else ExitCode.INVALID_RUN)
    except (ValueError, OSError) as exc:
        print(f"error: {exc}")
        return int(ExitCode.INVALID_PROVIDER)
    except Exception:
        print("error: unexpected internal failure")
        return int(ExitCode.INTERNAL_FAILURE)

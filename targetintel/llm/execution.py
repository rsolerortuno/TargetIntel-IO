"""Provider-neutral, single-invocation execution boundary for LLM requests."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable

from .contracts import LLMProvider, LLMRequest, LLMResponse, LLMResultStatus, ProviderProvenance
from .errors import ProviderErrorCategory


Clock = Callable[[], datetime]


@dataclass(frozen=True)
class ExecutionResult:
    """One operational provider result, separate from evidence processing."""

    request: LLMRequest
    response: LLMResponse
    executed: bool
    started_at: datetime
    finished_at: datetime

    @property
    def status(self) -> LLMResultStatus:
        return self.response.status


def _now(clock: Clock | None) -> datetime:
    value = (clock or (lambda: datetime.now(timezone.utc)))()
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("clock must return a timezone-aware datetime")
    return value.astimezone(timezone.utc)


def not_executed_result(request: LLMRequest, provider_name: str, model_name: str, *, clock: Clock | None = None, message: str = "Execution was not requested") -> ExecutionResult:
    """Create an explicit planning state without calling a provider."""
    started_at = _now(clock)
    provenance = ProviderProvenance(
        request.request_id, provider_name, model_name, None, request.prompt_id,
        request.prompt_version, request.response_schema_id,
        request.response_schema_version, request.task_type, request.source_document_id,
        LLMResultStatus.NOT_EXECUTED, ProviderErrorCategory.NOT_EXECUTED,
        requested_model_name=model_name,
    )
    response = LLMResponse(provenance, error_message=message)
    return ExecutionResult(request, response, False, started_at, _now(clock))


def execute_request(request: LLMRequest, provider: LLMProvider, *, clock: Clock | None = None) -> ExecutionResult:
    """Invoke ``provider`` exactly once; retries and fallback are intentionally absent."""
    if not isinstance(request, LLMRequest):
        raise TypeError("request must be an LLMRequest")
    if not isinstance(provider, LLMProvider):
        raise TypeError("provider must implement LLMProvider")
    started_at = _now(clock)
    response = provider.generate(request)
    if not isinstance(response, LLMResponse):
        raise TypeError("provider returned an invalid response")
    return ExecutionResult(request, response, True, started_at, _now(clock))

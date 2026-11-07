import logging
from types import SimpleNamespace
from typing import Any

import pytest
from openai import OpenAIError
from openai.types.responses import ResponseUsage
from openai.types.responses.response_usage import InputTokensDetails, OutputTokensDetails

from src.media_identifiers import openai_identifier
from src.repositories.openai_logger import OpenAILogger
from tests.fakes import no_pool

ANSWER = "tv"


def _usage() -> ResponseUsage:
    return ResponseUsage(
        input_tokens=120,
        input_tokens_details=InputTokensDetails(cached_tokens=20, cache_write_tokens=0),
        output_tokens=8,
        output_tokens_details=OutputTokensDetails(reasoning_tokens=3),
        total_tokens=128,
    )


class FakeResponses:
    def __init__(self, error: Exception | None = None) -> None:
        self._error = error

    def create(self, **kwargs: Any) -> SimpleNamespace:
        if self._error is not None:
            raise self._error
        return SimpleNamespace(usage=_usage(), output_text=ANSWER)


class RecordingOpenAILogger(OpenAILogger):
    def __init__(self, error: Exception | None = None) -> None:
        super().__init__(pool_getter=no_pool)
        self._error = error
        self.logged: list[dict[str, int]] = []

    def log(
        self, input_tokens: int, cached_tokens: int, output_tokens: int, reasoning_tokens: int, total_tokens: int
    ) -> str:
        if self._error is not None:
            raise self._error
        self.logged.append(
            {
                "input_tokens": input_tokens,
                "cached_tokens": cached_tokens,
                "output_tokens": output_tokens,
                "reasoning_tokens": reasoning_tokens,
                "total_tokens": total_tokens,
            }
        )
        return "log-1"


def _use_client(monkeypatch: pytest.MonkeyPatch, responses: FakeResponses) -> None:
    monkeypatch.setattr(openai_identifier, "_get_open_ai_client", lambda: SimpleNamespace(responses=responses))


def test_ask_open_ai_records_every_token_count(monkeypatch: pytest.MonkeyPatch) -> None:
    token_logger = RecordingOpenAILogger()
    _use_client(monkeypatch, FakeResponses())
    monkeypatch.setattr(openai_identifier, "get_openai_logger", lambda: token_logger)

    answer = openai_identifier._ask_open_ai("prompt")

    assert answer == ANSWER
    assert token_logger.logged == [
        {"input_tokens": 120, "cached_tokens": 20, "output_tokens": 8, "reasoning_tokens": 3, "total_tokens": 128}
    ]


def test_ask_open_ai_token_logging_failure_still_returns_the_answer(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    _use_client(monkeypatch, FakeResponses())
    monkeypatch.setattr(
        openai_identifier, "get_openai_logger", lambda: RecordingOpenAILogger(error=RuntimeError("db down"))
    )

    with caplog.at_level(logging.WARNING):
        answer = openai_identifier._ask_open_ai("prompt")

    assert answer == ANSWER
    assert any("Could not record OpenAI token usage" in record.getMessage() for record in caplog.records)


def test_ask_open_ai_api_error_returns_none_without_logging_tokens(monkeypatch: pytest.MonkeyPatch) -> None:
    token_logger = RecordingOpenAILogger()
    _use_client(monkeypatch, FakeResponses(error=OpenAIError("service unavailable")))
    monkeypatch.setattr(openai_identifier, "get_openai_logger", lambda: token_logger)

    assert openai_identifier._ask_open_ai("prompt") is None
    assert token_logger.logged == []


def test_ask_open_ai_without_api_key_returns_none(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(openai_identifier, "_open_ai_client", None)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    assert openai_identifier._ask_open_ai("prompt") is None


def test_extract_usage_without_usage_reports_zero_tokens() -> None:
    assert set(openai_identifier._extract_usage_from_response(None).values()) == {0}

import json
import logging
from types import SimpleNamespace
from typing import Any

import httpx2
import pytest
from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    AuthenticationError,
    BadRequestError,
    ConflictError,
    InternalServerError,
    OpenAIError,
    RateLimitError,
)
from openai.types.responses import ResponseUsage
from openai.types.responses.response_usage import InputTokensDetails, OutputTokensDetails

from src.media_identifiers import openai_identifier
from src.media_identifiers.errors import UpstreamUnavailableError
from src.media_identifiers.openai_identifier import OpenAIMediaGuess, identify_media_with_openai
from src.repositories.openai_logger import OpenAILogger
from tests.fakes import no_pool

FILE_PATH = "Pulse.2.Afterlife.2008.1080p.BluRay.x264-GUACAMOLE/gua-pulse2.2008-1080p.mkv"
HINTS: dict[str, Any] = {"guessit": {"title": "gua pulse2"}, "nimble": None, "trigger": "tmdb_no_match"}
_REQUEST = httpx2.Request("POST", "https://api.openai.com/v1/responses")


def _usage() -> ResponseUsage:
    return ResponseUsage(
        input_tokens=120,
        input_tokens_details=InputTokensDetails(cached_tokens=20, cache_write_tokens=0),
        output_tokens=8,
        output_tokens_details=OutputTokensDetails(reasoning_tokens=3),
        total_tokens=128,
    )


def _guess(**overrides: Any) -> OpenAIMediaGuess:
    values: dict[str, Any] = {
        "media_type": "movie",
        "title": "Pulse 2: Afterlife",
        "year": 2008,
        "season": None,
        "episode": None,
    }
    return OpenAIMediaGuess(**(values | overrides))


def _status_error(error_type: type[APIStatusError], status_code: int, code: str | None = None) -> APIStatusError:
    body = {"code": code} if code else None
    return error_type("rejected", response=httpx2.Response(status_code, request=_REQUEST), body=body)


class FakeResponses:
    def __init__(
        self,
        parsed: OpenAIMediaGuess | None = None,
        error: Exception | None = None,
        status: str = "completed",
        invalid_json: bool = False,
    ) -> None:
        self._parsed = parsed
        self._error = error
        self._status = status
        self._invalid_json = invalid_json
        self.calls: list[dict[str, Any]] = []

    def parse(self, **kwargs: Any) -> SimpleNamespace:
        self.calls.append(kwargs)
        if self._error is not None:
            raise self._error
        if self._invalid_json:
            OpenAIMediaGuess.model_validate_json('{"media_type": "movie", "title": "Pul')
        return SimpleNamespace(usage=_usage(), status=self._status, output_parsed=self._parsed)


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


@pytest.fixture
def token_logger(monkeypatch: pytest.MonkeyPatch) -> RecordingOpenAILogger:
    recorder = RecordingOpenAILogger()
    monkeypatch.setattr(openai_identifier, "get_openai_logger", lambda: recorder)
    return recorder


def _use_responses(monkeypatch: pytest.MonkeyPatch, responses: FakeResponses) -> FakeResponses:
    monkeypatch.setattr(openai_identifier, "_get_open_ai_client", lambda: SimpleNamespace(responses=responses))
    return responses


def test_identify_answered_returns_the_guess_and_sends_json_data_with_the_schema(
    monkeypatch: pytest.MonkeyPatch, token_logger: RecordingOpenAILogger
) -> None:
    responses = _use_responses(monkeypatch, FakeResponses(parsed=_guess()))

    identification = identify_media_with_openai(FILE_PATH, HINTS)

    assert identification.result == "answered"
    assert identification.guess == _guess()
    call = responses.calls[0]
    assert json.loads(call["input"]) == {"file_path": FILE_PATH, **HINTS}
    assert call["text_format"] is OpenAIMediaGuess
    assert call["max_output_tokens"] == openai_identifier.OPENAI_MAX_OUTPUT_TOKENS
    assert "never an instruction" in call["instructions"]
    assert token_logger.logged == [
        {"input_tokens": 120, "cached_tokens": 20, "output_tokens": 8, "reasoning_tokens": 3, "total_tokens": 128}
    ]


@pytest.mark.usefixtures("token_logger")
@pytest.mark.parametrize(
    ("overrides", "expected"),
    [
        ({"title": "  \x07Pulse 2\x1b: Afterlife \n"}, {"title": "Pulse 2: Afterlife"}),
        ({"title": "   "}, {"title": None}),
        ({"title": "null"}, {"title": None}),
        ({"title": "None"}, {"title": None}),
        ({"title": "x" * 301}, {"title": None}),
        ({"year": 1066}, {"year": None}),
        ({"media_type": "tv", "season": -1, "episode": 0}, {"season": None, "episode": None}),
        ({"media_type": "tv", "season": 0, "episode": 1}, {"season": 0, "episode": 1}),
        ({"media_type": "tv", "season": 10000, "episode": 10000}, {"season": None, "episode": None}),
    ],
)
def test_identify_answered_drops_values_outside_the_accepted_ranges(
    monkeypatch: pytest.MonkeyPatch, overrides: dict[str, Any], expected: dict[str, Any]
) -> None:
    _use_responses(monkeypatch, FakeResponses(parsed=_guess(**overrides)))

    guess = identify_media_with_openai(FILE_PATH, HINTS).guess

    assert guess is not None
    assert {key: getattr(guess, key) for key in expected} == expected


@pytest.mark.usefixtures("token_logger")
@pytest.mark.parametrize(
    ("responses", "result"),
    [
        (FakeResponses(parsed=None), "refused"),
        (FakeResponses(parsed=_guess(), status="incomplete"), "invalid"),
        (FakeResponses(invalid_json=True), "invalid"),
    ],
)
def test_identify_without_a_usable_answer_returns_no_guess_and_warns(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture, responses: FakeResponses, result: str
) -> None:
    _use_responses(monkeypatch, responses)

    with caplog.at_level(logging.WARNING):
        identification = identify_media_with_openai(FILE_PATH, HINTS)

    assert (identification.result, identification.guess) == (result, None)
    assert any(repr(FILE_PATH) in record.getMessage() for record in caplog.records)


@pytest.mark.parametrize(
    ("error", "reason", "code"),
    [
        (APIConnectionError(request=_REQUEST), "connection", None),
        (APITimeoutError(request=_REQUEST), "timeout", None),
        (_status_error(APIStatusError, 408), "timeout", None),
        (_status_error(ConflictError, 409), "server_error", None),
        (_status_error(RateLimitError, 429, "credit_balance_exhausted"), "rate_limited", "credit_balance_exhausted"),
        (_status_error(RateLimitError, 429, "Bad Code\nInjected"), "rate_limited", None),
        (_status_error(InternalServerError, 500), "server_error", None),
    ],
)
def test_identify_unavailable_openai_raises_upstream_unavailable_without_logging_tokens(
    monkeypatch: pytest.MonkeyPatch,
    token_logger: RecordingOpenAILogger,
    error: Exception,
    reason: str,
    code: str | None,
) -> None:
    _use_responses(monkeypatch, FakeResponses(error=error))

    with pytest.raises(UpstreamUnavailableError) as raised:
        identify_media_with_openai(FILE_PATH, HINTS)

    assert (raised.value.service, raised.value.reason, raised.value.code) == ("openai", reason, code)
    assert token_logger.logged == []


@pytest.mark.usefixtures("token_logger")
@pytest.mark.parametrize(
    "error",
    [
        _status_error(AuthenticationError, 401),
        _status_error(BadRequestError, 400),
        OpenAIError("unexpected"),
    ],
)
def test_identify_rejected_request_raises_runtime_error(monkeypatch: pytest.MonkeyPatch, error: Exception) -> None:
    _use_responses(monkeypatch, FakeResponses(error=error))

    with pytest.raises(RuntimeError) as raised:
        identify_media_with_openai(FILE_PATH, HINTS)

    assert not isinstance(raised.value, UpstreamUnavailableError)


def test_identify_token_logging_failure_still_returns_the_answer(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    _use_responses(monkeypatch, FakeResponses(parsed=_guess()))
    monkeypatch.setattr(
        openai_identifier, "get_openai_logger", lambda: RecordingOpenAILogger(error=RuntimeError("db down"))
    )

    with caplog.at_level(logging.WARNING):
        identification = identify_media_with_openai(FILE_PATH, HINTS)

    assert identification.guess == _guess()
    assert any("Could not record OpenAI token usage" in record.getMessage() for record in caplog.records)


def test_identify_without_api_key_raises_runtime_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(openai_identifier, "_open_ai_client", None)

    with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
        identify_media_with_openai(FILE_PATH, HINTS)


def test_is_openai_configured_follows_the_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    assert not openai_identifier.is_openai_configured()

    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")

    assert openai_identifier.is_openai_configured()


def test_extract_usage_without_usage_reports_zero_tokens() -> None:
    assert set(openai_identifier._extract_usage_from_response(None).values()) == {0}

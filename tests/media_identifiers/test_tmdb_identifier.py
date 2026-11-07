import logging
from typing import Any

import pytest
import requests

from src.media_identifiers import tmdb_identifier


class FakeResponse(requests.Response):
    def __init__(self, status_code: int, body: str = "{}") -> None:
        super().__init__()
        self.status_code = status_code
        self._content = body.encode()


@pytest.fixture(autouse=True)
def tmdb_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(tmdb_identifier, "_tmdb_api_key", None)
    monkeypatch.setenv("TMDB_API_KEY", "test-key")
    monkeypatch.setattr(tmdb_identifier.time, "sleep", lambda seconds: None)


def _queue_responses(monkeypatch: pytest.MonkeyPatch, *outcomes: requests.Response | Exception) -> list[str]:
    calls: list[str] = []
    pending = list(outcomes)

    def fake_get(url: str, **kwargs: Any) -> requests.Response:
        calls.append(url)
        outcome = pending.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    monkeypatch.setattr(tmdb_identifier.requests, "get", fake_get)
    return calls


def test_make_request_returns_the_decoded_body(monkeypatch: pytest.MonkeyPatch) -> None:
    _queue_responses(monkeypatch, FakeResponse(200, '{"id": 95480}'))

    assert tmdb_identifier._make_request("https://api.themoviedb.org/3/tv/95480") == {"id": 95480}


def test_make_request_retries_once_after_rate_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _queue_responses(monkeypatch, FakeResponse(429), FakeResponse(200, '{"id": 95480}'))

    result = tmdb_identifier._make_request("https://api.themoviedb.org/3/tv/95480")

    assert result == {"id": 95480}
    assert len(calls) == 2


def test_make_request_connection_error_after_rate_limit_logs_the_429_status(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    _queue_responses(monkeypatch, FakeResponse(429), requests.ConnectionError("connection reset"))

    with caplog.at_level(logging.ERROR):
        result = tmdb_identifier._make_request("https://api.themoviedb.org/3/tv/95480")

    assert result is None
    assert any("status [429]" in record.getMessage() for record in caplog.records)


def test_make_request_http_error_returns_none(monkeypatch: pytest.MonkeyPatch) -> None:
    _queue_responses(monkeypatch, FakeResponse(404))

    assert tmdb_identifier._make_request("https://api.themoviedb.org/3/movie/0") is None


def test_request_tmdb_external_ids_rejects_unknown_media_type() -> None:
    with pytest.raises(ValueError):
        tmdb_identifier.request_tmdb_external_ids(95480, "podcast")

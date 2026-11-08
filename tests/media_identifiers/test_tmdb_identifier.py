from typing import Any

import pytest
import requests

from src.media_identifiers import tmdb_identifier
from src.media_identifiers.errors import UpstreamUnavailableError
from src.secret_store import SecretsError

SERIES_URL = "https://api.themoviedb.org/3/tv/95480"


class FakeResponse(requests.Response):
    def __init__(self, status_code: int, body: str = "{}") -> None:
        super().__init__()
        self.status_code = status_code
        self._content = body.encode()


@pytest.fixture(autouse=True)
def tmdb_key(monkeypatch: pytest.MonkeyPatch, secret_values: dict[str, str]) -> None:
    secret_values["MEDIA_IDENTIFIER_TMDB_API_KEY"] = "test-key"
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

    assert tmdb_identifier._make_request(SERIES_URL) == {"id": 95480}


def test_make_request_sends_the_trimmed_api_key(monkeypatch: pytest.MonkeyPatch, secret_values: dict[str, str]) -> None:
    secret_values["MEDIA_IDENTIFIER_TMDB_API_KEY"] = " test-key\n"
    sent_headers: list[dict[str, str]] = []

    def fake_get(url: str, **kwargs: Any) -> requests.Response:
        sent_headers.append(kwargs["headers"])
        return FakeResponse(200, '{"id": 95480}')

    monkeypatch.setattr(tmdb_identifier.requests, "get", fake_get)

    tmdb_identifier._make_request(SERIES_URL)

    assert sent_headers[0]["Authorization"] == "Bearer test-key"


def test_make_request_retries_once_after_rate_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _queue_responses(monkeypatch, FakeResponse(429), FakeResponse(200, '{"id": 95480}'))

    result = tmdb_identifier._make_request(SERIES_URL)

    assert result == {"id": 95480}
    assert len(calls) == 2


def test_make_request_not_found_returns_none(monkeypatch: pytest.MonkeyPatch) -> None:
    _queue_responses(monkeypatch, FakeResponse(404))

    assert tmdb_identifier._make_request("https://api.themoviedb.org/3/movie/0") is None


@pytest.mark.parametrize(
    ("outcomes", "reason"),
    [
        ((requests.Timeout("read timed out"),), "timeout"),
        ((requests.ConnectionError("connection reset"),), "connection"),
        ((FakeResponse(429), requests.ConnectionError("connection reset")), "connection"),
        ((requests.exceptions.ChunkedEncodingError("connection broken"),), "connection"),
        ((FakeResponse(429), FakeResponse(429)), "rate_limited"),
        ((FakeResponse(503),), "server_error"),
        ((FakeResponse(200, "<html>maintenance</html>"),), "invalid_response"),
    ],
)
def test_make_request_unavailable_tmdb_raises_upstream_unavailable_with_the_reason(
    monkeypatch: pytest.MonkeyPatch, outcomes: tuple[requests.Response | Exception, ...], reason: str
) -> None:
    _queue_responses(monkeypatch, *outcomes)

    with pytest.raises(UpstreamUnavailableError) as raised:
        tmdb_identifier._make_request(SERIES_URL)

    assert (raised.value.service, raised.value.reason) == ("tmdb", reason)


@pytest.mark.parametrize("status_code", [400, 401])
def test_make_request_rejected_request_raises_runtime_error_naming_status_and_path(
    monkeypatch: pytest.MonkeyPatch, status_code: int
) -> None:
    _queue_responses(monkeypatch, FakeResponse(status_code))

    with pytest.raises(RuntimeError, match=rf"HTTP {status_code} for /3/tv/95480$") as raised:
        tmdb_identifier._make_request(SERIES_URL, {"query": "Slow Horses"})

    assert not isinstance(raised.value, UpstreamUnavailableError)


def test_make_request_without_api_key_raises_before_calling_tmdb(
    monkeypatch: pytest.MonkeyPatch, secret_values: dict[str, str]
) -> None:
    del secret_values["MEDIA_IDENTIFIER_TMDB_API_KEY"]
    calls = _queue_responses(monkeypatch)

    with pytest.raises(SecretsError, match="MEDIA_IDENTIFIER_TMDB_API_KEY"):
        tmdb_identifier._make_request(SERIES_URL)

    assert calls == []


def test_request_tmdb_external_ids_rejects_unknown_media_type() -> None:
    with pytest.raises(ValueError):
        tmdb_identifier.request_tmdb_external_ids(95480, "podcast")

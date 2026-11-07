import json
import logging
from typing import Any

import pytest
import requests

from src.media_identifiers import nimble_classifier
from src.media_identifiers.nimble_classifier import NimbleVerdict, classify_media_kind, get_nimble_url

ROM_FILE = "/watch/Retro/NES/Balloon Fight (JU) [o5].nes"


class FakeResponse(requests.Response):
    def __init__(self, status_code: int, body: str) -> None:
        super().__init__()
        self.status_code = status_code
        self._content = body.encode()


class RecordingPost:
    def __init__(self, outcome: requests.Response | Exception) -> None:
        self.outcome = outcome
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def __call__(self, url: str, **kwargs: Any) -> requests.Response:
        self.calls.append((url, kwargs))
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return self.outcome


def _answer(choice: object, confidence: object) -> str:
    return json.dumps(
        {"model": "nimble", "answers": {"kind": {"type": "choice", "choice": choice, "confidence": confidence}}}
    )


@pytest.fixture
def nimble(secret_values: dict[str, str]) -> None:
    secret_values["MEDIA_IDENTIFIER_NIMBLE_URL"] = "http://nimble.example:11434/"


def _use_post(monkeypatch: pytest.MonkeyPatch, outcome: requests.Response | Exception) -> RecordingPost:
    post = RecordingPost(outcome)
    monkeypatch.setattr(nimble_classifier.requests, "post", post)
    return post


@pytest.mark.usefixtures("nimble")
def test_classify_media_kind_returns_the_verdict_and_sends_the_triage_question(monkeypatch: pytest.MonkeyPatch) -> None:
    post = _use_post(monkeypatch, FakeResponse(200, _answer("other", 0.99)))

    verdict = classify_media_kind(ROM_FILE)

    assert verdict == NimbleVerdict("other", 0.99)
    url, kwargs = post.calls[0]
    assert url == "http://nimble.example:11434/v1/systemone"
    assert kwargs["json"]["model"] == "nimble"
    assert kwargs["json"]["state"] == ROM_FILE
    assert set(kwargs["json"]["questions"]["kind"]["criteria"]) == {"movie", "tv", "other"}
    assert kwargs["allow_redirects"] is False
    assert kwargs["timeout"] == nimble_classifier.NIMBLE_TIMEOUT_SECONDS


def test_classify_media_kind_without_nimble_url_sends_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    post = _use_post(monkeypatch, FakeResponse(200, _answer("movie", 1.0)))

    assert classify_media_kind(ROM_FILE) is None
    assert post.calls == []


@pytest.mark.usefixtures("nimble")
@pytest.mark.parametrize(
    "outcome",
    [
        requests.Timeout("read timed out"),
        requests.ConnectionError("connection refused"),
        FakeResponse(500, '{"error": "model failed"}'),
        FakeResponse(301, ""),
        FakeResponse(200, "not json"),
        FakeResponse(200, '{"answers": {}}'),
        FakeResponse(200, '["unexpected"]'),
        FakeResponse(200, _answer("podcast", 0.9)),
        FakeResponse(200, _answer("movie", 1.5)),
        FakeResponse(200, _answer("movie", True)),
        FakeResponse(200, _answer("movie", "0.9")),
    ],
)
def test_classify_media_kind_unusable_answer_returns_none_and_warns_naming_the_file(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture, outcome: requests.Response | Exception
) -> None:
    _use_post(monkeypatch, outcome)

    with caplog.at_level(logging.WARNING):
        verdict = classify_media_kind(ROM_FILE)

    assert verdict is None
    assert any(record.levelno == logging.WARNING and repr(ROM_FILE) in record.getMessage() for record in caplog.records)


def test_verdict_is_confident_from_the_threshold() -> None:
    assert NimbleVerdict("movie", nimble_classifier.NIMBLE_MIN_CONFIDENCE).is_confident
    assert not NimbleVerdict("movie", nimble_classifier.NIMBLE_MIN_CONFIDENCE - 0.01).is_confident


def test_get_nimble_url_strips_the_trailing_slash(secret_values: dict[str, str]) -> None:
    secret_values["MEDIA_IDENTIFIER_NIMBLE_URL"] = " https://nimble.example:11434/ "

    assert get_nimble_url() == "https://nimble.example:11434"


@pytest.mark.parametrize(
    "value",
    [
        "ftp://nimble.example",
        "http://user:secret@nimble.example:11434",
        "http://",
        "nimble.example:11434",
        "http://nimble.example:99999",
        "http://nimble.example:11434?secret=1",
        "http://nimble.example:11434#secret",
    ],
)
def test_get_nimble_url_invalid_value_raises_without_echoing_it(secret_values: dict[str, str], value: str) -> None:
    secret_values["MEDIA_IDENTIFIER_NIMBLE_URL"] = value

    with pytest.raises(ValueError, match="MEDIA_IDENTIFIER_NIMBLE_URL must be") as raised:
        get_nimble_url()

    assert "secret" not in str(raised.value)

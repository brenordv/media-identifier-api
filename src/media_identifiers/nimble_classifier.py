"""Client for the Nimble classifier, which decides whether a file path names a movie, a TV release, or neither."""

import os
from dataclasses import dataclass
from typing import Literal, cast
from urllib.parse import urlsplit

import requests
from opentelemetry import trace

from src.utils import get_otel_log_handler

NimbleChoice = Literal["movie", "tv", "other"]

NIMBLE_MODEL = "nimble"
NIMBLE_MIN_CONFIDENCE = 0.8
"""Verdicts below this confidence never change the media type or reject a file."""

NIMBLE_TIMEOUT_SECONDS = (3, 15)
"""Connect and read timeouts. A warm call takes about half a second; the read timeout leaves room for a model reload."""

_CHOICES: tuple[NimbleChoice, ...] = ("movie", "tv", "other")

_QUESTION = {
    "kind": {
        "type": "choice",
        "instructions": "Classify what this file path belongs to.",
        "criteria": {
            "movie": "A movie release: the video file itself, or a part of its archive (.rar, .r00, .7z, .zip)",
            "tv": "A TV series release (one episode, several, or a season pack): the video or an archive part",
            "other": (
                "Not a movie or TV release: a game or ROM (.nes, .gba, .rvz, .iso of a game), an image, "
                "a document, software"
            ),
        },
    }
}

_logger = get_otel_log_handler("NimbleClassifier")


@dataclass(frozen=True)
class NimbleVerdict:
    """Nimble's answer for one file path.

    Attributes:
        choice: ``movie``, ``tv`` or ``other`` (not a movie or TV release).
        confidence: Nimble's confidence in the choice, from 0 to 1.
    """

    choice: NimbleChoice
    confidence: float

    @property
    def is_confident(self) -> bool:
        """True when the confidence reaches :data:`NIMBLE_MIN_CONFIDENCE`."""
        return self.confidence >= NIMBLE_MIN_CONFIDENCE


def get_nimble_url() -> str | None:
    """Return the Nimble base URL from ``NIMBLE_URL``, without a trailing slash.

    Returns:
        The URL, or None when ``NIMBLE_URL`` is unset or empty (Nimble is then not used).

    Raises:
        ValueError: If the value is not an http or https URL with a host, an optional valid port and path, and no
            credentials, query or fragment.
    """
    value = os.environ.get("NIMBLE_URL", "").strip()
    if not value:
        return None

    message = "NIMBLE_URL must be an http or https URL with a host and without credentials, query or fragment."
    parts = urlsplit(value)
    try:
        parts.port
    except ValueError as e:
        raise ValueError(message) from e
    if (
        parts.scheme not in ("http", "https")
        or not parts.hostname
        or parts.username
        or parts.password
        or parts.query
        or parts.fragment
    ):
        raise ValueError(message)

    return value.rstrip("/")


@_logger.trace("classify_media_kind")
def classify_media_kind(file_path: str) -> NimbleVerdict | None:
    """Ask Nimble whether a file path names a movie, a TV release, or neither.

    Args:
        file_path: The file name or path to classify.

    Returns:
        The verdict, or None when Nimble is not configured or gave no usable answer (each failure logged as a
        warning).

    Raises:
        ValueError: If ``NIMBLE_URL`` is set to an invalid value.
    """
    base_url = get_nimble_url()
    if base_url is None:
        return None

    try:
        response = requests.post(
            f"{base_url}/v1/systemone",
            json={"model": NIMBLE_MODEL, "state": file_path, "questions": _QUESTION},
            timeout=NIMBLE_TIMEOUT_SECONDS,
            allow_redirects=False,
        )
    except requests.RequestException as e:
        _warn_no_verdict(file_path, type(e).__name__)
        return None

    if response.status_code != 200:
        _warn_no_verdict(file_path, f"HTTP {response.status_code}")
        return None

    try:
        answer = response.json()["answers"]["kind"]
        choice = answer["choice"]
        confidence = answer["confidence"]
    except (requests.JSONDecodeError, KeyError, TypeError) as e:
        _warn_no_verdict(file_path, f"unexpected body ({type(e).__name__})")
        return None

    if choice not in _CHOICES:
        _warn_no_verdict(file_path, f"unknown choice {choice!r:.80}")
        return None

    if isinstance(confidence, bool) or not isinstance(confidence, int | float) or not 0 <= confidence <= 1:
        _warn_no_verdict(file_path, f"invalid confidence {confidence!r:.80}")
        return None

    verdict = NimbleVerdict(cast(NimbleChoice, choice), float(confidence))

    span = trace.get_current_span()
    if span.is_recording():
        span.set_attributes({"nimble.choice": verdict.choice, "nimble.confidence": verdict.confidence})

    return verdict


def _warn_no_verdict(file_path: str, reason: str) -> None:
    # Best-effort: Nimble is optional, so a failure is logged and never raised.
    span = trace.get_current_span()
    if span.is_recording():
        span.set_attribute("nimble.error", reason)
    _logger.warning(f"Nimble gave no verdict for {file_path!r}: {reason}")

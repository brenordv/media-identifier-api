"""Normalization of the many spellings of "movie" and "TV" that guessit, TMDB, OpenAI and callers produce."""

from collections.abc import Mapping
from typing import Any

from src.media_identifiers.constants import MOVIE, TV, VALID_MEDIA_TYPES
from src.utils import get_otel_log_handler

_logger = get_otel_log_handler("MediaIdentifier")

_MEDIA_TYPE_ALIASES = {
    "tv show": TV,
    "tv shows": TV,
    "tv": TV,
    "tvshow": TV,
    "tv-show": TV,
    "series": TV,
    "episode": TV,
    "scripted": TV,
    "film": MOVIE,
    "movie": MOVIE,
    "movies": MOVIE,
}


@_logger.trace("normalize_media_type")
def normalize_media_type(value: str | None) -> str | None:
    """Map a media type spelling to ``movie`` or ``tv``.

    Args:
        value: Any spelling, e.g. ``"Episode"``, ``"tv-show"``, ``"Film"``.

    Returns:
        ``movie``, ``tv``, or None when the value is not recognized.
    """
    if value is None:
        return None

    normalized = value.strip().lower()
    if normalized in VALID_MEDIA_TYPES:
        return normalized

    replaced = normalized.replace("-", " ").replace("_", " ").strip()
    if replaced in _MEDIA_TYPE_ALIASES:
        return _MEDIA_TYPE_ALIASES[replaced]

    squeezed = replaced.replace(" ", "")
    if squeezed in _MEDIA_TYPE_ALIASES:
        return _MEDIA_TYPE_ALIASES[squeezed]

    return None


def is_movie(media_type: str | None) -> bool:
    """True when ``media_type`` normalizes to ``movie``."""
    return normalize_media_type(media_type) == MOVIE


def is_tv(media_type: str | None) -> bool:
    """True when ``media_type`` normalizes to ``tv``."""
    return normalize_media_type(media_type) == TV


def is_media_type_valid(media_type: str | None) -> bool:
    """True when ``media_type`` normalizes to ``movie`` or ``tv``."""
    return normalize_media_type(media_type) in VALID_MEDIA_TYPES


def is_record_of_media_type(record: Mapping[str, Any], media_type: str | None) -> bool:
    """True when ``record["media_type"]`` is the valid media type ``media_type`` (any accepted spelling of either)."""
    expected = normalize_media_type(media_type)
    return expected is not None and normalize_media_type(record.get("media_type")) == expected

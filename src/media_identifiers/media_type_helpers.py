from __future__ import annotations

from typing import Optional

from src.media_identifiers.constants import MOVIE, TV, VALID_MEDIA_TYPES

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


def normalize_media_type(value: Optional[str]) -> Optional[str]:
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


def is_movie(media_type: Optional[str]) -> bool:
    return normalize_media_type(media_type) == MOVIE


def is_tv(media_type: Optional[str]) -> bool:
    return normalize_media_type(media_type) == TV


def is_media_type_valid(media_type: Optional[str]) -> bool:
    return normalize_media_type(media_type) in VALID_MEDIA_TYPES


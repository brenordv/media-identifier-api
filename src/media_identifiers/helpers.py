from __future__ import annotations

from typing import Optional, Tuple

from src.models.media_info import MediaInfoBuilder
from src.utils import get_otel_log_handler

_logger = get_otel_log_handler("MediaIdentifierHelpers")


def apply_basic_media_attributes(
    builder: MediaInfoBuilder,
    *,
    title: Optional[str],
    media_type: Optional[str],
    year: Optional[int],
    season: Optional[int] = None,
    episode: Optional[int] = None,
    searchable_reference: Optional[str] = None,
) -> MediaInfoBuilder:
    if title:
        normalized_title = title.strip()
        if normalized_title:
            builder = (
                builder.with_title(normalized_title)
                .with_original_title(normalized_title)
            )
            searchable_reference = searchable_reference or normalized_title

    if searchable_reference:
        builder = builder.with_searchable_reference(searchable_reference)

    if media_type is not None:
        builder = builder.with_media_type(media_type)

    if year is not None:
        builder = builder.with_year(year)

    if season is not None:
        builder = builder.with_season(season)

    if episode is not None:
        builder = builder.with_episode(episode)

    return builder


def parse_season_episode_string(
    value: Optional[str],
    *,
    logger=None,
) -> Tuple[Optional[int], Optional[int]]:
    if value is None:
        return None, None

    raw_value = value.strip()
    if raw_value == "":
        return None, None

    active_logger = logger or _logger

    try:
        parts = [segment.strip() for segment in raw_value.split(",")]
        if len(parts) != 2:
            active_logger.error(f"Invalid season/episode format: {value}")
            return None, None

        season_number = _extract_number(parts[0], "season", active_logger)
        episode_number = _extract_number(parts[1], "episode", active_logger)

        if season_number is None or episode_number is None:
            return None, None

        return season_number, episode_number
    except Exception as exc:  # noqa: BLE001
        active_logger.error(f"Failed to parse season/episode value '{value}': {exc}")
        return None, None


def _extract_number(segment: str, label: str, logger) -> Optional[int]:
    tokens = [part.strip() for part in segment.split(":")]
    if len(tokens) != 2 or not tokens[1].isdigit():
        logger.error(f"Invalid {label} format: {segment}")
        return None
    return int(tokens[1])


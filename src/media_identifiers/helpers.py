"""Media record helpers: filling a record builder and parsing ``"season:X, episode:Y"`` answers."""

from simple_log_factory_ext_otel import TracedLogger

from src.models.media_info import MediaInfoBuilder
from src.utils import get_otel_log_handler

_logger = get_otel_log_handler("MediaIdentifierHelpers")


@_logger.trace("apply_basic_media_attributes")
def apply_basic_media_attributes(
    builder: MediaInfoBuilder,
    *,
    title: str | None,
    media_type: str | None,
    year: int | None,
    season: int | None = None,
    episode: int | None = None,
    searchable_reference: str | None = None,
) -> MediaInfoBuilder:
    """Copy the basic identification fields into a builder, skipping empty values.

    The stripped title is used as both title and original title, and as the search key when no
    ``searchable_reference`` is given.

    Returns:
        The same builder.
    """
    if title:
        normalized_title = title.strip()
        if normalized_title:
            builder = builder.with_title(normalized_title).with_original_title(normalized_title)
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


@_logger.trace("parse_season_episode_string")
def parse_season_episode_string(
    value: str | None,
    *,
    logger: TracedLogger | None = None,
) -> tuple[int | None, int | None]:
    """Parse an answer shaped like ``"season:1, episode:2"``.

    Args:
        value: The text to parse.
        logger: Logger for malformed values; defaults to this module's logger.

    Returns:
        ``(season, episode)``, or ``(None, None)`` when the value is empty or malformed.
    """
    if value is None:
        return None, None

    raw_value = value.strip()
    if raw_value == "":
        return None, None

    active_logger = logger or _logger

    parts = [segment.strip() for segment in raw_value.split(",")]
    if len(parts) != 2:
        active_logger.warning(f"Invalid season/episode format: {value!r}")
        return None, None

    season_number = _extract_number(parts[0], "season", active_logger)
    episode_number = _extract_number(parts[1], "episode", active_logger)

    if season_number is None or episode_number is None:
        return None, None

    return season_number, episode_number


def _extract_number(segment: str, label: str, logger: TracedLogger) -> int | None:
    tokens = [part.strip() for part in segment.split(":")]
    if len(tokens) != 2 or not tokens[1].isdecimal():
        logger.warning(f"Invalid {label} format: {segment!r}")
        return None
    return int(tokens[1])

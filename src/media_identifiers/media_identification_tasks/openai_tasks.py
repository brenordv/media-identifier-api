"""Identification tasks backed by OpenAI: media type and title, and season/episode numbers."""

from src.media_identifiers.helpers import parse_season_episode_string
from src.media_identifiers.media_type_helpers import (
    is_media_type_valid,
    is_movie,
)
from src.media_identifiers.openai_identifier import (
    identify_media_type_with_open_ai,
    identify_movie_title_with_open_ai,
    identify_series_season_episode_with_open_ai,
    identify_series_title_with_open_ai,
)
from src.models.media_info import MediaData, merge_media_info
from src.utils import get_otel_log_handler

_logger = get_otel_log_handler("OpenAI Task")

TaskResult = tuple[MediaData | None, bool]
"""The (possibly updated) media record and whether the task succeeded."""


@_logger.trace("openai_identify_series_season_and_episode_by_title")
def openai_identify_series_season_and_episode_by_title(
    media_data: MediaData | None, *, file_path: str | None = None
) -> TaskResult:
    """Ask OpenAI for the season and episode numbers of a TV file.

    Args:
        media_data: The media identified so far; must already carry its TMDB series id.
        file_path: The file name to analyze.

    Returns:
        The record with ``season``/``episode`` merged in (None when OpenAI could not tell), and True; or the input
        and False when there is no media, no file path, or no TMDB series id.
    """
    log_tag = openai_identify_series_season_and_episode_by_title.__name__

    if media_data is None:
        _logger.debug(f"[{log_tag}] No media provided. Skipping task.")
        return None, False

    if media_data.get("season") is not None and media_data.get("episode") is not None:
        _logger.debug(f"[{log_tag}] Season/episode already identified. Skipping task.")
        return media_data, True

    if file_path is None:
        _logger.debug(f"[{log_tag}] No file path provided. Skipping task.")
        return None, False

    if media_data.get("tmdb_series_id") is None:
        _logger.debug(f"[{log_tag}] No TMDb series ID found in media data. Task failed.")
        return media_data, False

    season, episode = parse_season_episode_string(
        identify_series_season_episode_with_open_ai(file_path),
        logger=_logger,
    )

    return merge_media_info(media_data, {"season": season, "episode": episode, "used_openai": True}), True


@_logger.trace("openai_run_basic_identification_by_filename")
def openai_run_basic_identification_by_filename(
    media_data: MediaData | None, *, file_path: str | None = None
) -> TaskResult:
    """Ask OpenAI whether a file is a movie or a TV episode, then for its title.

    Args:
        media_data: The media identified so far, if any.
        file_path: The file name to analyze.

    Returns:
        The record with ``media_type``, ``title`` and ``used_openai`` merged in, and True; or the input and False
        when there is no file path or OpenAI returned no valid media type.
    """
    log_tag = openai_run_basic_identification_by_filename.__name__

    if file_path is None:
        _logger.debug(f"[{log_tag}] No file path provided. Skipping task.")
        return media_data, False

    media_type = identify_media_type_with_open_ai(file_path)

    if not is_media_type_valid(media_type):
        _logger.debug(f"[{log_tag}] No media type found for file: [{file_path!r}]. Skipping task.")
        return media_data, False

    _logger.debug(f"[{log_tag}] Media type identified as: {media_type!r}")

    if is_movie(media_type):
        title = identify_movie_title_with_open_ai(file_path)
    else:
        title = identify_series_title_with_open_ai(file_path)

    return merge_media_info(media_data, {"title": title, "media_type": media_type, "used_openai": True}), True

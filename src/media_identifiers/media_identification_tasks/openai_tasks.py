from simple_log_factory.log_factory import log_factory

from src.media_identifiers.media_identification_tasks.tmdb_tasks import tmdb_identify_movie_by_id, \
    tmdb_identify_series_by_id
from src.media_identifiers.openai_identifier import identify_movie_title_with_open_ai, \
    identify_series_title_with_open_ai, identify_series_season_episode_with_open_ai
from src.media_identifiers.tmdb_identifier import request_tmdb_series_episode_details
from src.models.media_info import merge_media_info

_logger = log_factory("OpenAI Task", unique_handler_types=True)


def openai_identify_movie_by_title(media_data: dict, **kwargs):
    """
    Tries to identify a movie with OpenAI by title.
    If successful, it will try to get the details for that movie using the TMDb ID
    by calling tmdb_identify_movie_by_id.
    """
    log_tag = openai_identify_movie_by_title.__name__

    if kwargs.get('success', False):
        _logger.debug(f"[{log_tag}] Not necessary to run this. Skipping task.")
        return media_data, True

    if media_data is None:
        _logger.debug(f"[{log_tag}] No media provided. Skipping task.")
        return None, False

    file_path = kwargs.get('file_path')

    if file_path is None:
        _logger.debug(f"[{log_tag}] No file path provided. Skipping task.")
        return None, False

    title = identify_movie_title_with_open_ai(file_path)

    if title is None:
        _logger.debug(f"[{log_tag}] No title found for file: [{file_path}]. Skipping task.")
        return None, False

    return tmdb_identify_movie_by_id(media_data)

def openai_identify_series_by_title(media_data: dict, **kwargs):
    """
    Tries to identify a series with OpenAI by title.
    If successful, it will try to get the details for that movie using the TMDb ID
    by calling tmdb_identify_series_by_id.
    """
    log_tag = openai_identify_series_by_title.__name__

    if kwargs.get('success', False):
        _logger.debug(f"[{log_tag}] Not necessary to run this. Skipping task.")
        return media_data, True

    if media_data is None:
        _logger.debug(f"[{log_tag}] No media provided. Skipping task.")
        return None, False

    file_path = kwargs.get('file_path')

    if file_path is None:
        _logger.debug(f"[{log_tag}] No file path provided. Skipping task.")
        return None, False

    title = identify_series_title_with_open_ai(file_path)

    if title is None:
        _logger.debug(f"[{log_tag}] No title found for file: [{file_path}]. Skipping task.")
        return None, False

    tmdb_id = media_data.get('tmdb_id')

    if tmdb_id is None:
        _logger.debug(f"[{log_tag}] No TMDb ID found in media data. Task failed.")
        return media_data, False

    season, episode = _parse_season_episode(identify_series_season_episode_with_open_ai(file_path))

    if season is not None and episode is not None:
        _logger.debug(f"[{log_tag}] No season/episode found for file: [{file_path}]. Skipping task.")

        episode_details = request_tmdb_series_episode_details(tmdb_id, season, episode)

        if episode_details is None:
            _logger.debug(f"[{log_tag}] No episode details found for TMDb ID: [{tmdb_id}]. Skipping task.")
            return media_data, False

        media_data = merge_media_info(media_data, episode_details)

        return media_data, True

    return tmdb_identify_series_by_id(media_data)


def _parse_season_episode(data):
    parts = data.split(',')
    if len(parts) != 2:
        _logger.error(f"Invalid season/episode format: {data}")
        return None, None

    season_parts = parts[0].strip().split(':')

    if len(season_parts) != 2 or not season_parts[1].isdigit():
        _logger.error(f"Invalid season format: {season_parts}")
        return None, None

    season = int(season_parts[1])

    episode_parts = parts[1].strip().split(':')

    if len(episode_parts) != 2 or not episode_parts[1].isdigit():
        _logger.error(f"Invalid episode format: {episode_parts}")
        return None, None

    episode = int(episode_parts[1])

    return season, episode

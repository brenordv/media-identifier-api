from simple_log_factory.log_factory import log_factory

from src.media_identifiers.openai_identifier import identify_movie_title_with_open_ai, \
    identify_series_title_with_open_ai, identify_series_season_episode_with_open_ai, identify_media_type_with_open_ai
from src.models.media_info import merge_media_info

_logger = log_factory("OpenAI Task", unique_handler_types=True)

def openai_identify_series_season_and_episode_by_title(media_data: dict, **kwargs):
    """
    Tries to identify an episode's season and episode number with OpenAI.
    If successful, it will try to get the details for that movie using the TMDb ID
    by calling tmdb_identify_series_by_id.
    """
    log_tag = openai_identify_series_season_and_episode_by_title.__name__

    if media_data is None:
        _logger.debug(f"[{log_tag}] No media provided. Skipping task.")
        return None, False

    season = media_data.get('season')
    episode = media_data.get('episode')

    if season is not None and episode is not None:
        _logger.debug(f"[{log_tag}] Season/episode already identified. Skipping task.")
        return media_data, True

    file_path = kwargs.get('file_path')

    if file_path is None:
        _logger.debug(f"[{log_tag}] No file path provided. Skipping task.")
        return None, False

    tmdb_id = media_data.get('tmdb_id')

    if tmdb_id is None:
        _logger.debug(f"[{log_tag}] No TMDb ID found in media data. Task failed.")
        return media_data, False

    season, episode = _parse_season_episode(identify_series_season_episode_with_open_ai(file_path))

    return merge_media_info(media_data, {
        "season": season,
        "episode": episode,
        "used_openai": True
    })


def openai_run_basic_identification_by_filename(media_data: dict, **kwargs):
    """
    Tries to identify if the file is a movie or a series, and its title.
    """
    log_tag = openai_run_basic_identification_by_filename.__name__

    file_path = kwargs.get('file_path')

    if file_path is None:
        _logger.debug(f"[{log_tag}] No file path provided. Skipping task.")
        return media_data, False

    media_type = identify_media_type_with_open_ai(file_path)

    if media_type is None or media_type not in ['movie', 'tv']:
        _logger.debug(f"[{log_tag}] No media type found for file: [{file_path}]. Skipping task.")
        return media_data, False

    _logger.debug(f"[{log_tag}] Media type identified as: {media_type}")

    if media_type == 'movie':
        title = identify_movie_title_with_open_ai(file_path)
    else:
        title = identify_series_title_with_open_ai(file_path)

    return merge_media_info(media_data, {
        "title": title,
        "media_type": media_type,
        "used_openai": True
    }), True


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

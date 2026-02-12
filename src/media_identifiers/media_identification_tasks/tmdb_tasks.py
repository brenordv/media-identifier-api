from src.media_identifiers.constants import MOVIE, TV
from src.media_identifiers.media_type_helpers import normalize_media_type
from src.media_identifiers.tmdb_identifier import identify_media_with_tmdb_movie_search, request_tmdb_movie_details, \
    request_tmdb_external_ids, identify_media_with_tmdb_series_search, request_tmdb_series_details, \
    request_tmdb_series_episode_details
from src.models.media_info import merge_media_info
from src.utils import get_otel_log_handler

_logger = get_otel_log_handler("TMDB Task")


def tmdb_identify_movie_by_id(media_data: dict, **kwargs):
    """
    Tries to identify a movie with TMDB by title and then gets the details for that movie using the TMDb ID.
    """
    log_tag = tmdb_identify_movie_by_id.__name__

    if media_data is None:
        _logger.debug(f"[{log_tag}] No media provided. Skipping task.")
        return None, False

    title = media_data.get('title')
    year = media_data.get('year')

    search_result = identify_media_with_tmdb_movie_search(title, year)
    if search_result is None:
        _logger.debug(f"[{log_tag}] No search result found for title: [{title}]. Skipping task. Retry is allowed.")
        return media_data, False

    tmdb_id = search_result.get('tmdb_id')

    if tmdb_id is None:
        _logger.debug(f"[{log_tag}] No TMDb ID found in search result for title: [{title}]. Skipping task. Retry is allowed.")
        return media_data, False

    movie_details = request_tmdb_movie_details(tmdb_id)
    if movie_details is None:
        _logger.debug(f"[{log_tag}] No movie details found for TMDb ID: [{tmdb_id}]. Skipping task. Retry is allowed.")
        return media_data, False

    return merge_media_info(media_data, movie_details), True


def tmdb_get_movie_external_ids(media_data: dict, **kwargs):
    """
    Uses TMDB api to get external ids for a movie.
    """
    log_tag = tmdb_get_movie_external_ids.__name__

    if not kwargs.get('success', False):
        _logger.debug(f"[{log_tag}] Can't run this step if it came from failure. Skipping task.")
        return media_data, False

    return _tmdb_get_media_external_ids(media_data, **kwargs, media_type=MOVIE)


def tmdb_identify_series_by_title_and_id(media_data: dict, **kwargs):
    """
    Tries to identify a series with TMDB by title and then gets the details for that show using the TMDb ID.
    """
    log_tag = tmdb_identify_series_by_title_and_id.__name__

    if media_data is None:
        _logger.debug(f"[{log_tag}] No media provided. Skipping task.")
        return None, False

    title = media_data.get('title')
    year = media_data.get('year')
    search_result = identify_media_with_tmdb_series_search(title, year)

    if search_result is None:
        _logger.debug(f"[{log_tag}] No search result found for title: [{title}]. Skipping task. Retry is allowed.")
        return media_data, False

    tmdb_id = search_result.get('tmdb_id')

    if tmdb_id is None:
        _logger.debug(f"[{log_tag}] No TMDb ID found in search result for title: [{title}]. Skipping task. Retry is allowed.")
        return media_data, False

    series_details = request_tmdb_series_details(tmdb_id)
    if series_details is None:
        _logger.debug(f"[{log_tag}] No series details found for TMDb ID: [{tmdb_id}]. Skipping task. Retry is allowed.")
        return media_data, False

    return merge_media_info(media_data, series_details), True


def tmdb_get_series_external_ids(media_data: dict, **kwargs):
    """
    Uses TMDB api to get external ids for a movie.
    """
    log_tag = tmdb_get_series_external_ids.__name__

    if not kwargs.get('success', False):
        _logger.debug(f"[{log_tag}] Can't run this step if it came from failure. Skipping task.")
        return media_data, False

    external_ids, success = _tmdb_get_media_external_ids(media_data, **kwargs, media_type=TV)

    if not success:
        _logger.error(f"[{log_tag}] Failed to get external IDs for media: {media_data}")
        return media_data, False

    external_ids['tmdb_id'] = None  # Cleaning this so it won't override the episode id.

    return merge_media_info(media_data, external_ids), True


def tmdb_get_episode_details(media_data: dict, **kwargs):
    """
    Uses TMDB api to get the episode details.
    """
    log_tag = tmdb_get_episode_details.__name__

    if not kwargs.get('success', False):
        _logger.debug(f"[{log_tag}] Can't run this step if it came from failure. Skipping task.")
        return media_data, False

    tmdb_id = media_data.get('tmdb_id')
    season = media_data.get('season')
    episode = media_data.get('episode')

    if tmdb_id is None:
        _logger.debug(f"[{log_tag}] No TMDb ID found in media data. Task failed.")
        return media_data, False

    if season is None or episode is None:
        _logger.debug(f"[{log_tag}] No season or episode number found in media data. Task failed.")
        return media_data, False

    episode_details = request_tmdb_series_episode_details(tmdb_id, season, episode)

    if episode_details is None:
        _logger.debug(f"[{log_tag}] No episode details found for TMDb ID: [{tmdb_id}]. Skipping task.")
        return media_data, False

    return merge_media_info(media_data, episode_details), True


def _tmdb_get_media_external_ids(media_data: dict, **kwargs):
    """
    Uses TMDB api to get external ids for a movie.
    """
    log_tag = _tmdb_get_media_external_ids.__name__

    tmdb_id = media_data.get('tmdb_id')

    if tmdb_id is None:
        _logger.debug(f"[{log_tag}] No TMDb ID found in media data. Task failed.")
        return media_data, False

    media_type = normalize_media_type(media_data.get('media_type'))

    if media_type is None:
        _logger.debug(f"[{log_tag}] No media type found in media data. Task failed.")
        return media_data, False

    external_ids = request_tmdb_external_ids(tmdb_id, media_type)

    if external_ids is None:
        _logger.debug(f"[{log_tag}] No external IDs found for TMDb ID: [{tmdb_id}]. Task failed.")
        return media_data, False

    external_ids['tmdb_id'] = None  # Cleaning this so it won't override the episode id.

    return merge_media_info(media_data, external_ids), True
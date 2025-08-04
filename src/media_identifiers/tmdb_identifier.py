import os
import random
import time
from typing import Dict, Any, Optional
import requests
from simple_log_factory.log_factory import log_factory

from src.models.media_info import MediaInfoBuilder

_tmdb_api_key = None
_logger = log_factory("MediaIdentifier", unique_handler_types=True)

def identify_media_with_tmdb(query: str, media_type: str) -> Optional[Dict[str, Any]]:
    if query is None or not query.strip():
        raise ValueError("Query string must not be empty or None.")

    if media_type == "movie":
        return _identify_media_with_tmdb_movie_search(query)
    elif media_type == "tv":
        return _identify_media_with_tmdb_series_search(query)

    return _identify_media_with_tmdb_multi_search(query)


def request_tmdb_movie_details(tmdb_id: int) -> Optional[Dict[str, Any]]:
    if not tmdb_id:
        raise ValueError("TMDB ID must not be None or empty.")

    movie_details = _make_request(f'https://api.themoviedb.org/3/movie/{tmdb_id}')

    if not movie_details:
        _logger.warning(f"No details found for TMDB ID: {tmdb_id}")
        return None

    return _get_record_builder_for_tmdb_data(movie_details) \
        .with_media_type('movie') \
        .build()

def request_tmdb_series_details(tmdb_id: int) -> Optional[Dict[str, Any]]:
    if not tmdb_id:
        raise ValueError("TMDB ID must not be None or empty.")

    series_details = _make_request(f'https://api.themoviedb.org/3/tv/{tmdb_id}')

    if not series_details:
        _logger.warning(f"No details found for TMDB ID: {tmdb_id}")
        return None

    return _get_record_builder_for_tmdb_data(series_details) \
        .with_media_type('tv') \
        .build()


def request_tmdb_series_episode_details(tmdb_id: int, season: int, episode: int) -> Optional[Dict[str, Any]]:
    if not tmdb_id:
        raise ValueError("TMDB ID must not be None or empty.")

    if not season or not episode:
        raise ValueError("Season and episode numbers must not be None or empty.")

    episode_details = _make_request(f'https://api.themoviedb.org/3/tv/{tmdb_id}/season/{season}/episode/{episode}')

    if not episode_details:
        _logger.warning(f"No details found for TMDB ID: {tmdb_id}")
        return None

    return MediaInfoBuilder() \
        .with_episode_title(episode_details.get('name')) \
        .with_episode(episode_details.get('episode_number', episode)) \
        .with_season(episode_details.get('season_number', season)) \
        .with_media_type('tv') \
        .with_tmdb_episode_id(episode_details.get('id')) \
        .with_overview(episode_details.get('overview')) \
        .with_year(_extract_year_from_tmdb_multi_data(episode_details)) \
        .build()


def request_tmdb_external_ids(tmdb_id: int, media_type: str) -> Optional[Dict[str, Any]]:
    if not tmdb_id:
        raise ValueError("TMDB ID must not be None or empty.")

    if media_type not in ['movie', 'tv']:
        raise ValueError("Media type must be either 'movie' or 'tv'.")

    external_ids = _make_request(f'https://api.themoviedb.org/3/{media_type}/{tmdb_id}/external_ids')

    if not external_ids:
        _logger.warning(f"No external IDs found for TMDB ID: {tmdb_id}")
        return None

    return MediaInfoBuilder() \
        .with_tmdb_id(tmdb_id) \
        .with_imdb_id(external_ids.get('imdb_id')) \
        .with_tvdb_id(external_ids.get('tvdb_id')) \
        .with_tvrage_id(external_ids.get('tvrage_id')) \
        .with_wikidata_id(external_ids.get('wikidata_id')) \
        .with_facebook_id(external_ids.get('facebook_id')) \
        .with_instagram_id(external_ids.get('instagram_id')) \
        .with_twitter_id(external_ids.get('twitter_id')) \
        .build()


def _identify_media_with_tmdb_multi_search(query: str) -> Optional[Dict[str, Any]]:
    return _identify_media_with_tmdb_by_type(query, 'multi').build()


def _identify_media_with_tmdb_movie_search(query: str) -> Optional[Dict[str, Any]]:
    result = _identify_media_with_tmdb_by_type(query, 'movie')
    if result is None:
        return None
    return result.with_media_type('movie').build()

def _identify_media_with_tmdb_series_search(query: str) -> Optional[Dict[str, Any]]:
    result = _identify_media_with_tmdb_by_type(query, 'tv')
    if result is None:
        return None
    return result.with_media_type('tv').build()


def _identify_media_with_tmdb_by_type(query: str, media_type: str) -> MediaInfoBuilder:
    params = {
        'query': query,
        'include_adult': True,
        'page': 1
    }

    response_data = _make_request(f'https://api.themoviedb.org/3/search/{media_type}', params)

    if not response_data or 'results' not in response_data or not response_data['results']:
        _logger.warning(f"No results found for query: {query}")
        return None

    tmdb_multi_data = response_data['results'][0]

    return _get_record_builder_for_tmdb_data(tmdb_multi_data)

def _get_tmdb_api_key():
    global _tmdb_api_key

    if _tmdb_api_key:
        _logger.debug("Using cached TMDB API key.")
        return _tmdb_api_key

    _logger.debug("Loading TMDB API key from environment variables.")

    _tmdb_api_key = os.getenv('TMDB_API_KEY')

    if not _tmdb_api_key:
        raise ValueError("TMDB API key is not set in the environment variables.")

    return _tmdb_api_key


def _prepare_tmdb_headers():
    return {
        'Authorization': f'Bearer {_get_tmdb_api_key()}',
        'Content-Type': 'application/json'
    }


def _prepare_tmdb_parameters(params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Prepare parameters for TMDB API requests.

    Args:
        params (Dict[str, Any]): The parameters to prepare.

    Returns:
        Dict[str, Any]: The prepared parameters with default language set.
    """
    if params is None:
        params = {}

    if 'language' not in params:
        params['language'] = 'en-US'

    return params


def _get_debounce_time():
    base_wait_time = 8
    min_jitter = 1
    max_jitter = 3
    jitter = random.uniform(min_jitter, max_jitter)
    return base_wait_time + jitter


def _make_request(url: str, params: Dict[str, Any] = None) -> Optional[Dict[str, Any]]:
    response = None

    try:
        headers = _prepare_tmdb_headers()
        params = _prepare_tmdb_parameters(params)

        response = requests.get(url, params=params, headers=headers, timeout=10)

        if response.status_code == 429:
            debounce_time = _get_debounce_time()

            _logger.warning(f"TMDB API rate limit exceeded. Retrying after {debounce_time} seconds.")
            time.sleep(debounce_time)

            response = requests.get(url, params=params, headers=headers, timeout=10)

        response.raise_for_status()

        return response.json()

    except requests.Timeout:
        _logger.error(f"TMDB API request timed out for url: {url}")

    except requests.HTTPError as e:
        _logger.error(f"TMDB API HTTP error for url: {url}: {e}")

    except requests.RequestException as e:
        status_code = response.status_code if response else 'unknown'
        _logger.error(f"TMDB API request failed with status [{status_code}] for url: [{url}]: {e}")

    except ValueError as e:
        _logger.error(f"Warning: Failed to parse TMDB API response for url: {url}: {e}")

    return None


def _extract_year_from_tmdb_multi_data(tmdb_multi_data: Dict[str, Any]) -> Optional[int]:
    for date_key in ['release_date', 'first_air_date', 'air_date']:
        if date_key in tmdb_multi_data and tmdb_multi_data[date_key]:
            date_value = tmdb_multi_data[date_key]
            if not date_value:
                continue
            return int(date_value[:4])

    return None


def _get_record_builder_for_tmdb_data(tmdb_data: Dict[str, Any]) -> MediaInfoBuilder:
    return MediaInfoBuilder() \
        .with_title(tmdb_data.get('title', tmdb_data.get('name'))) \
        .with_original_title(tmdb_data.get('original_title', tmdb_data.get('original_name'))) \
        .with_tmdb_id(tmdb_data.get('id')) \
        .with_overview(tmdb_data.get('overview')) \
        .with_year(_extract_year_from_tmdb_multi_data(tmdb_data)) \
        .with_media_type(tmdb_data.get('media_type')) \
        .with_original_language(tmdb_data.get('original_language')) \
        .with_genres(tmdb_data.get('genre_ids', tmdb_data.get('genres'))) \
        .with_used_tmdb(True)

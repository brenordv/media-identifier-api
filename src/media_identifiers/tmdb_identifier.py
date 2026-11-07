"""Calls to the TMDB v3 API: search, movie/series/episode details and external ids."""

import os
import random
import time
from typing import Any
from urllib.parse import urlsplit

import requests
from opentelemetry import trace

from src.media_identifiers.constants import MOVIE, TV
from src.media_identifiers.errors import UpstreamUnavailableError
from src.media_identifiers.media_type_helpers import normalize_media_type
from src.models.media_info import MediaData, MediaInfoBuilder
from src.utils import get_otel_log_handler, is_valid_year

TMDB_API_BASE_URL = "https://api.themoviedb.org/3"
REQUEST_TIMEOUT_SECONDS = 10
RATE_LIMIT_BASE_WAIT_SECONDS = 8
RATE_LIMIT_JITTER_SECONDS = (1, 3)

_tmdb_api_key: str | None = None
_logger = get_otel_log_handler("MediaIdentifier")


@_logger.trace("request_tmdb_movie_details")
def request_tmdb_movie_details(tmdb_id: int) -> MediaData | None:
    """Fetch a movie's details.

    Args:
        tmdb_id: TMDB movie id.

    Returns:
        The movie record, or None when TMDB returns nothing.

    Raises:
        ValueError: If ``tmdb_id`` is empty.
        UpstreamUnavailableError: If TMDB is unavailable.
        RuntimeError: If TMDB rejects the request.
    """
    span = trace.get_current_span()
    if span.is_recording():
        span.set_attribute("tmdb.id", tmdb_id)

    if not tmdb_id:
        raise ValueError("TMDB ID must not be None or empty.")

    movie_details = _make_request(f"{TMDB_API_BASE_URL}/movie/{tmdb_id}")

    if not movie_details:
        _logger.warning(f"No details found for TMDB ID: {tmdb_id}")
        return None

    return _get_record_builder_for_tmdb_data(movie_details).with_media_type(MOVIE).build()


@_logger.trace("request_tmdb_series_details")
def request_tmdb_series_details(tmdb_series_id: int) -> MediaData | None:
    """Fetch a series' details.

    Args:
        tmdb_series_id: TMDB series id.

    Returns:
        The series record, or None when TMDB returns nothing. The series id is in ``tmdb_series_id``; ``tmdb_id`` is
        left empty because on a TV record it holds the episode id.

    Raises:
        ValueError: If ``tmdb_series_id`` is empty.
        UpstreamUnavailableError: If TMDB is unavailable.
        RuntimeError: If TMDB rejects the request.
    """
    span = trace.get_current_span()
    if span.is_recording():
        span.set_attribute("tmdb.series_id", tmdb_series_id)

    if not tmdb_series_id:
        raise ValueError("TMDB series ID must not be None or empty.")

    series_details = _make_request(f"{TMDB_API_BASE_URL}/tv/{tmdb_series_id}")

    if not series_details:
        _logger.warning(f"No details found for TMDB series ID: {tmdb_series_id}")
        return None

    return (
        _get_record_builder_for_tmdb_data(series_details)
        .with_media_type(TV)
        .with_tmdb_series_id(tmdb_series_id)
        .with_tmdb_id(None)
        .build()
    )


@_logger.trace("request_tmdb_series_episode_details")
def request_tmdb_series_episode_details(tmdb_series_id: int, season: int, episode: int) -> MediaData | None:
    """Fetch one episode's details.

    Args:
        tmdb_series_id: TMDB series id.
        season: Season number; 0 is the series' specials.
        episode: Episode number.

    Returns:
        The episode record (episode id in ``tmdb_id``, series id in ``tmdb_series_id``), or None when TMDB returns
        nothing.

    Raises:
        ValueError: If the series id is empty, or the season or episode is missing.
        UpstreamUnavailableError: If TMDB is unavailable.
        RuntimeError: If TMDB rejects the request.
    """
    span = trace.get_current_span()
    if span.is_recording():
        span.set_attributes({"tmdb.series_id": tmdb_series_id, "media.season": season, "media.episode": episode})

    if not tmdb_series_id:
        raise ValueError("TMDB series ID must not be None or empty.")

    if season is None or episode is None:
        raise ValueError("Season and episode numbers must not be None.")

    episode_details = _make_request(f"{TMDB_API_BASE_URL}/tv/{tmdb_series_id}/season/{season}/episode/{episode}")

    if not episode_details:
        _logger.warning(f"No details found for TMDB series ID {tmdb_series_id} S{season}E{episode}")
        return None

    return (
        MediaInfoBuilder()
        .with_episode_title(episode_details.get("name"))
        .with_episode(episode_details.get("episode_number", episode))
        .with_season(episode_details.get("season_number", season))
        .with_media_type(TV)
        .with_tmdb_id(episode_details.get("id"))
        .with_tmdb_series_id(tmdb_series_id)
        .with_overview(episode_details.get("overview"))
        .with_year(_extract_year_from_tmdb_multi_data(episode_details))
        .build()
    )


@_logger.trace("request_tmdb_external_ids")
def request_tmdb_external_ids(
    tmdb_id: int,
    media_type: str,
    season_number: int | None = None,
    episode_number: int | None = None,
) -> MediaData | None:
    """Fetch the external ids (IMDb, TheTVDB, Wikidata, social) of a movie, a series or an episode.

    Args:
        tmdb_id: TMDB movie id, or series id for TV.
        media_type: ``movie`` or ``tv`` (any spelling ``normalize_media_type`` accepts).
        season_number: With ``episode_number``, asks for the episode's ids instead of the series'.
        episode_number: See ``season_number``.

    Returns:
        A record with only the external ids set (``tmdb_id`` stays empty, so merging it never changes the record's
        own id), or None when TMDB returns nothing.

    Raises:
        ValueError: If ``tmdb_id`` is empty or ``media_type`` is neither movie nor TV.
        UpstreamUnavailableError: If TMDB is unavailable.
        RuntimeError: If TMDB rejects the request.
    """
    span = trace.get_current_span()
    if span.is_recording():
        span.set_attributes({"tmdb.id": tmdb_id, "media.type": media_type})
        if season_number:
            span.set_attribute("media.season", season_number)
        if episode_number:
            span.set_attribute("media.episode", episode_number)

    if not tmdb_id:
        raise ValueError("TMDB ID must not be None or empty.")

    normalized_media_type = normalize_media_type(media_type)

    if normalized_media_type == TV:
        if season_number is not None and episode_number is not None:
            url = f"{TMDB_API_BASE_URL}/tv/{tmdb_id}/season/{season_number}/episode/{episode_number}/external_ids"
        else:
            url = f"{TMDB_API_BASE_URL}/tv/{tmdb_id}/external_ids"
    elif normalized_media_type == MOVIE:
        url = f"{TMDB_API_BASE_URL}/movie/{tmdb_id}/external_ids"
    else:
        raise ValueError(f"Media type must be either '{MOVIE}' or '{TV}'.")

    external_ids = _make_request(url)

    if not external_ids:
        _logger.warning(f"No external IDs found for TMDB ID: {tmdb_id}")
        return None

    return (
        MediaInfoBuilder()
        .with_imdb_id(external_ids.get("imdb_id"))
        .with_tvdb_id(external_ids.get("tvdb_id"))
        .with_tvrage_id(external_ids.get("tvrage_id"))
        .with_wikidata_id(external_ids.get("wikidata_id"))
        .with_facebook_id(external_ids.get("facebook_id"))
        .with_instagram_id(external_ids.get("instagram_id"))
        .with_twitter_id(external_ids.get("twitter_id"))
        .build()
    )


@_logger.trace("identify_media_with_tmdb_movie_search")
def identify_media_with_tmdb_movie_search(query: str | None, year: int | None = None) -> MediaData | None:
    """Search movies by title (and year when plausible) and return the first match.

    Returns:
        The first match as a movie record, or None when nothing matched.

    Raises:
        UpstreamUnavailableError: If TMDB is unavailable.
        RuntimeError: If TMDB rejects the request.
    """
    span = trace.get_current_span()
    if span.is_recording():
        span.set_attributes({"media.query": query, "media.year": year, "media.type": MOVIE})
    result = _identify_media_with_tmdb_by_type(query, MOVIE, year)
    if result is None:
        return None
    return result.with_media_type(MOVIE).build()


@_logger.trace("identify_media_with_tmdb_series_search")
def identify_media_with_tmdb_series_search(query: str | None, year: int | None = None) -> MediaData | None:
    """Search series by title (and first-air year when plausible) and return the first match.

    Returns:
        The first match as a TV record with the series id in ``tmdb_series_id`` (``tmdb_id`` empty), or None when
        nothing matched.

    Raises:
        UpstreamUnavailableError: If TMDB is unavailable.
        RuntimeError: If TMDB rejects the request.
    """
    span = trace.get_current_span()
    if span.is_recording():
        span.set_attributes({"media.query": query, "media.year": year, "media.type": TV})
    result = _identify_media_with_tmdb_by_type(query, TV, year)
    if result is None:
        return None

    series_data = result.with_media_type(TV).build()
    series_data["tmdb_series_id"] = series_data["tmdb_id"]
    series_data["tmdb_id"] = None

    return series_data


@_logger.trace("_identify_media_with_tmdb_by_type")
def _identify_media_with_tmdb_by_type(query: str | None, media_type: str, year: int | None) -> MediaInfoBuilder | None:
    params: dict[str, Any] = {"query": query, "include_adult": True, "page": 1}

    if is_valid_year(year):
        params["year"] = year

    response_data = _make_request(f"{TMDB_API_BASE_URL}/search/{media_type}", params)

    if not response_data or not response_data.get("results"):
        _logger.debug(f"No results found for query: {query!r}")
        return None

    return _get_record_builder_for_tmdb_data(response_data["results"][0])


def _get_tmdb_api_key() -> str:
    global _tmdb_api_key

    if _tmdb_api_key is not None and _tmdb_api_key.strip() != "":
        _logger.debug("Using cached TMDB API key.")
        return _tmdb_api_key

    _logger.debug("Loading TMDB API key from environment variables.")

    _tmdb_api_key = os.getenv("TMDB_API_KEY")

    if not _tmdb_api_key:
        raise ValueError("TMDB API key is not set in the environment variables.")

    return _tmdb_api_key


def _prepare_tmdb_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {_get_tmdb_api_key()}", "Content-Type": "application/json"}


def _prepare_tmdb_parameters(params: dict[str, Any] | None) -> dict[str, Any]:
    """Return the request parameters with ``language`` defaulting to ``en-US``."""
    prepared = dict(params) if params else {}
    prepared.setdefault("language", "en-US")
    return prepared


def _get_debounce_time() -> float:
    return RATE_LIMIT_BASE_WAIT_SECONDS + random.uniform(*RATE_LIMIT_JITTER_SECONDS)


@_logger.trace("_make_request")
def _make_request(url: str, params: dict[str, Any] | None = None) -> dict[str, Any] | None:
    """GET a TMDB endpoint, retrying once after a 429.

    Returns:
        The decoded JSON body, or None when TMDB answers 404 (the resource does not exist).

    Raises:
        ValueError: If the TMDB API key is not configured.
        UpstreamUnavailableError: If TMDB times out, cannot be reached, still answers 429 after the retry, answers 5xx,
            or returns a body that is not JSON.
        RuntimeError: If TMDB rejects the request with another 4xx (an invalid key, a malformed request).
    """
    span = trace.get_current_span()
    if span.is_recording():
        span.set_attribute("http.url", url)

    headers = _prepare_tmdb_headers()
    prepared_params = _prepare_tmdb_parameters(params)

    _logger.debug(f"TMDB API: About to make request to url: [{url}] Params: [{prepared_params!r}]")

    try:
        response = requests.get(url, params=prepared_params, headers=headers, timeout=REQUEST_TIMEOUT_SECONDS)

        if response.status_code == 429:
            debounce_time = _get_debounce_time()

            _logger.warning(f"TMDB API rate limit exceeded. Retrying after {debounce_time} seconds.")
            time.sleep(debounce_time)

            response = requests.get(url, params=prepared_params, headers=headers, timeout=REQUEST_TIMEOUT_SECONDS)
    except requests.Timeout as e:
        raise UpstreamUnavailableError("tmdb", "timeout") from e
    except (requests.ConnectionError, requests.exceptions.ChunkedEncodingError) as e:
        raise UpstreamUnavailableError("tmdb", "connection") from e

    _logger.debug(f"TMDB API: Got response [{response.status_code}] Body: [{response.text}]")

    status_code = response.status_code
    if status_code == 404:
        return None
    if status_code == 429:
        raise UpstreamUnavailableError("tmdb", "rate_limited")
    if status_code >= 500:
        raise UpstreamUnavailableError("tmdb", "server_error")
    if status_code >= 400:
        raise RuntimeError(f"TMDB rejected the request with HTTP {status_code} for {urlsplit(url).path}")

    try:
        body: dict[str, Any] = response.json()
    except requests.JSONDecodeError as e:
        raise UpstreamUnavailableError("tmdb", "invalid_response") from e
    return body


def _extract_year_from_tmdb_multi_data(tmdb_multi_data: dict[str, Any]) -> int | None:
    for date_key in ("release_date", "first_air_date", "air_date"):
        date_value = tmdb_multi_data.get(date_key)
        if date_value:
            return int(date_value[:4])

    return None


def _get_record_builder_for_tmdb_data(tmdb_data: dict[str, Any]) -> MediaInfoBuilder:
    return (
        MediaInfoBuilder()
        .with_title(tmdb_data.get("title", tmdb_data.get("name")))
        .with_original_title(tmdb_data.get("original_title", tmdb_data.get("original_name")))
        .with_tmdb_id(tmdb_data.get("id"))
        .with_overview(tmdb_data.get("overview"))
        .with_year(_extract_year_from_tmdb_multi_data(tmdb_data))
        .with_media_type(tmdb_data.get("media_type"))
        .with_original_language(tmdb_data.get("original_language"))
        .with_genres(tmdb_data.get("genre_ids", tmdb_data.get("genres")))
        .with_used_tmdb(True)
    )

from typing import Optional

from simple_log_factory.log_factory import log_factory

from src.media_identifiers.guessit_identifier import identify_media_with_guess_it
from src.media_identifiers.openai_identifier import identify_media_with_open_ai
from src.media_identifiers.tmdb_identifier import identify_media_with_tmdb_multi_search, request_tmdb_movie_details, \
    request_tmdb_series_details, request_tmdb_series_episode_details, request_tmdb_external_ids
from src.models.media_info import merge_media_info
from src.repositories.repository_factory import get_repository


class MediaIdentifier:
    def __init__(self):
        self._cache = get_repository('cache')
        self._logger = log_factory("MediaIdentifier", unique_handler_types=True)

    def identify_media(self, file_path: str) -> Optional[dict]:
        try:
            self._logger.debug(f"Identifying media file: {file_path}")

            media_data = identify_media_with_guess_it(file_path)

            if not media_data:
                self._logger.debug("GuessIt did not return any data, trying OpenAI for identification.")
                media_data = identify_media_with_open_ai(file_path)

            title = media_data.get('title')

            if not title:
                self._logger.warning(f"No title or media type found in media data for file: {file_path}")
                return None

            cached_data = self._cache.get_cached(search_term=title, search_prop_name="title")

            if cached_data:
                self._logger.debug(f"Found cached data for title: {title}")
                return cached_data

            tmdb_media = identify_media_with_tmdb_multi_search(title)

            if tmdb_media is None:
                self._logger.warning(f"No TMDb data found for title: [{title}]. Trying to identify with OpenAI.")
                openai_data = identify_media_with_open_ai(file_path)

                if openai_data is None:
                    self._logger.error(f"Neither TMDb or OpenAI were able to identify [{file_path}]/[{title}]. Skipping.")
                    return None

                title = openai_data.get('title')

                cached_data = self._cache.get_cached(search_term=title, search_prop_name="title")

                if cached_data:
                    self._logger.debug(f"After identifying file with OpenAI, we found cached data for title: {title}")
                    return cached_data

                tmdb_media = identify_media_with_tmdb_multi_search(title)

                if tmdb_media is None:
                    self._logger.error(f"Open AI found the title [{title}] but TMDb was unable to identify it. Failed to identify the file [{file_path}]. Skipping.]")
                    return None

                # We don't want to lose useful data from Guess IT
                media_data = merge_media_info(media_data, openai_data)

                # And now merging GuessIT + OpenAI with TMDb.
                media_data = merge_media_info(media_data, tmdb_media)

            else:
                media_data = merge_media_info(media_data, tmdb_media)

                title = media_data.get('title')

                cached_data = self._cache.get_cached(search_term=title, search_prop_name="title")

                if cached_data:
                    self._logger.debug(f"After identifying file with TMDB, we found cached data for title: {title}")
                    return cached_data

            media_type = media_data.get('media_type')

            tmdb_id = media_data.get('tmdb_id')

            if media_type == 'movie':
                movie_details = request_tmdb_movie_details(tmdb_id)
                media_data = merge_media_info(media_data, movie_details)
            elif media_type == 'tv':
                series_details = request_tmdb_series_details(tmdb_id)

                media_data = merge_media_info(media_data, series_details)

                if series_details:
                    season_number = media_data.get('season')
                    episode_number = media_data.get('episode')

                    if season_number is not None and episode_number is not None:
                        episode_details = request_tmdb_series_episode_details(tmdb_id, season_number, episode_number)
                        if episode_details:
                            media_data = merge_media_info(media_data, episode_details)

            if media_type == 'movie' or media_type == 'tv':
                external_ids = request_tmdb_external_ids(tmdb_id, media_type)
                media_data = merge_media_info(media_data, external_ids)

            return self._cache.cache_data(media_data)
        except Exception as e:
            self._logger.error(f"Error identifying media file {file_path}: {str(e)}")
            raise

from typing import Optional

from simple_log_factory.log_factory import log_factory

from src.media_identifiers.guessit_identifier import identify_media_with_guess_it
from src.media_identifiers.media_identification_tasks.pipeline_builders import build_movie_identification_pipeline, \
    build_series_identification_pipeline
from src.media_identifiers.openai_identifier import identify_media_with_open_ai
from src.media_identifiers.tmdb_identifier import request_tmdb_movie_details, \
    request_tmdb_series_details, request_tmdb_series_episode_details, request_tmdb_external_ids, \
    identify_media_with_tmdb
from src.models.media_info import merge_media_info, is_media_type_valid
from src.repositories.repository_factory import get_repository


class MediaIdentifier:
    def __init__(self):
        self._cache = get_repository('cache')
        self._logger = log_factory("MediaIdentifier", unique_handler_types=True)

    def identify_media(self, file_path: str) -> Optional[dict]:
        try:
            self._logger.debug(f"Identifying media file: {file_path}")

            # Basic guess using GuessIT
            media_data = identify_media_with_guess_it(file_path)

            if media_data is None:
                self._logger.debug("GuessIt did not return any data, trying OpenAI for identification.")
                media_data = identify_media_with_open_ai(file_path, media_type=None)

            if media_data is None:
                self._logger.error("GuessIT and OpenAI did not return any data. Giving up on this file.")
                return None

            cached_data = self._cache.get_cached_by_obj(media_data)

            if cached_data:
                title = media_data.get('title')
                self._logger.debug(f"Found cached data for object: {title}")

                return cached_data

            media_type = media_data.get('media_type')
            if not is_media_type_valid(media_type):
                self._logger.warning(f"Media type [{media_type}] is not valid. Skipping.")
                return None

            if media_type == 'movie':
                # Build a movie identification pipeline here.
                identification_pipeline = build_movie_identification_pipeline()

            else:
                # Build series identification pipeline here.
                identification_pipeline = build_series_identification_pipeline()

            result_data = media_data
            success = True

            for step in identification_pipeline:
                result_data, success = step(result_data, success=success, file_path=file_path)

            if not success:
                self._logger.error(f"Failed to identify media file {file_path} using pipeline.")
                return None

            return self._cache.cache_data(result_data)
        except Exception as e:
            self._logger.error(f"Error identifying media file {file_path}: {str(e)}")
            raise

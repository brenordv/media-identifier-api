from typing import Optional

from simple_log_factory.log_factory import log_factory

from src.media_identifiers.media_identification_tasks.guessit_tasks import identify_media_with_guess_it
from src.media_identifiers.media_identification_tasks.openai_tasks import openai_run_basic_identification_by_filename
from src.media_identifiers.media_identification_tasks.pipeline_builders import build_movie_identification_pipeline, \
    build_series_identification_pipeline
from src.models.media_info import is_media_type_valid
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
            # Double check with OpenAI
            media_data, id_success = openai_run_basic_identification_by_filename(media_data, file_path=file_path)

            if media_data is None or not id_success:
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

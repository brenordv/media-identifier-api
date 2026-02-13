from typing import Optional

from src.media_identifiers.media_type_helpers import is_media_type_valid, is_movie, is_tv
from src.media_identifiers.pipeline import PipelineContext, PipelineController, build_pipeline
from src.models.media_identification_request import MediaIdentificationRequest
from src.repositories.repository_factory import get_repository
from src.utils import get_otel_log_handler


_logger = get_otel_log_handler("MediaIdentifier")


class MediaIdentifier:
    def __init__(self):
        self._cache = get_repository("cache")
        self._logger = _logger

    @_logger.trace("identify")
    def identify(self, request: MediaIdentificationRequest) -> Optional[dict]:
        try:
            self._logger.debug(f"Starting identification: {request.to_logging_payload()}")

            context = PipelineContext(request, cache_repository=self._cache, logger=self._logger)
            handlers = build_pipeline(request)
            controller = PipelineController(handlers, logger=self._logger)
            result = controller.run(context)

            if result.cached is not None:
                self._logger.debug("Returning cached result from pipeline.")
                return result.cached

            media = result.media
            if not media:
                self._logger.debug("Pipeline produced no media data.")
                return None

            media_type = media.get("media_type")
            if not is_media_type_valid(media_type):
                self._logger.warning(f"Media type [{media_type}] is not valid. Skipping persistence.")
                return None

            return self._persist_media(media)
        except Exception as exc:  # noqa: BLE001
            self._logger.error(f"Error identifying media request {request.to_logging_payload()}: {exc}")
            raise

    @_logger.trace("get_media_info_by_filename")
    def get_media_info_by_filename(self, file_path: str) -> Optional[dict]:
        request = MediaIdentificationRequest.from_filename(file_path)
        return self.identify(request)

    @_logger.trace("get_media_info")
    def get_media_info(
        self,
        media_type: str,
        year: int,
        title: str,
        season: Optional[int],
        episode: Optional[int],
    ) -> Optional[dict]:
        request = MediaIdentificationRequest.from_metadata(
            media_type=media_type,
            year=year,
            title=title,
            season=season,
            episode=episode,
        )
        return self.identify(request)

    @_logger.trace("_persist_media")
    def _persist_media(self, media: dict) -> Optional[dict]:
        media_type = media.get("media_type")

        if is_movie(media_type):
            tmdb_id = media.get("tmdb_id")
            if tmdb_id is None:
                self._logger.debug("Movie media lacks TMDb ID; returning without caching.")
                return media

            existing = self._cache.get_cached_by_tmdb_id(tmdb_id)
            if existing:
                self._logger.debug("Movie already cached by TMDb ID.")
                return existing

            return self._cache.cache_data(media)

        if is_tv(media_type):
            tmdb_id = media.get("tmdb_id")
            season = media.get("season")
            episode = media.get("episode")
            tmdb_series_id = media.get("tmdb_series_id")

            if tmdb_id is not None:
                existing = self._cache.get_cached_by_tmdb_id(tmdb_id)
                if existing:
                    self._logger.debug("Episode already cached by TMDb ID.")
                    return existing

            if tmdb_series_id is not None and season is not None and episode is not None:
                existing = self._cache.get_cached_tv_episode(tmdb_series_id, season, episode)
                if existing:
                    self._logger.debug("Episode already cached by series/season/episode.")
                    return existing

            if tmdb_id is None:
                self._logger.debug("Episode lacks TMDb episode ID; returning without caching.")
                return media

            return self._cache.cache_data(media)

        self._logger.debug("Unknown media type; returning without caching.")
        return media

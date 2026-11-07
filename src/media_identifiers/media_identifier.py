"""Entry point of identification: runs the pipeline for a request and caches what it identifies."""

from src.media_identifiers.constants import MOVIE, TV
from src.media_identifiers.media_type_helpers import is_media_type_valid, is_movie, is_record_of_media_type, is_tv
from src.media_identifiers.pipeline import PipelineContext, PipelineController, build_pipeline
from src.models.media_identification_request import MediaIdentificationRequest
from src.models.media_info import MediaData
from src.repositories.media_info_cache import MediaInfoCache
from src.utils import get_otel_log_handler

_logger = get_otel_log_handler("MediaIdentifier")


class MediaIdentifier:
    """Identifies media from a file name or known metadata, using and filling the cache.

    Args:
        cache_repository: The media cache.
    """

    def __init__(self, cache_repository: MediaInfoCache) -> None:
        self._cache = cache_repository
        self._logger = _logger

    @_logger.trace("identify")
    def identify(self, request: MediaIdentificationRequest) -> MediaData | None:
        """Run the identification pipeline.

        Returns:
            The cached record when one matched, the identified (and, when possible, newly cached) record, or None
            when nothing valid was identified.

        Raises:
            PipelineExecutionError: If a pipeline step fails.
            RuntimeError: If the cache cannot be read or written.
        """
        self._logger.debug(f"Starting identification: {request.to_logging_payload()!r}")

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
            self._logger.warning(f"Media type [{media_type!r}] is not valid. Skipping persistence.")
            return None

        return self._persist_media(media)

    @_logger.trace("get_media_info_by_filename")
    def get_media_info_by_filename(self, file_path: str) -> MediaData | None:
        """Identify media from a file name or path (see :meth:`identify`)."""
        request = MediaIdentificationRequest.from_filename(file_path)
        return self.identify(request)

    @_logger.trace("get_media_info")
    def get_media_info(
        self,
        media_type: str,
        year: int,
        title: str,
        season: int | None,
        episode: int | None,
    ) -> MediaData | None:
        """Identify media from known metadata (see :meth:`identify`)."""
        request = MediaIdentificationRequest.from_metadata(
            media_type=media_type,
            year=year,
            title=title,
            season=season,
            episode=episode,
        )
        return self.identify(request)

    @_logger.trace("_persist_media")
    def _persist_media(self, media: MediaData) -> MediaData:
        media_type = media.get("media_type")

        if is_movie(media_type):
            return self._persist_movie(media)

        if is_tv(media_type):
            return self._persist_episode(media)

        self._logger.debug("Unknown media type; returning without caching.")
        return media

    def _persist_movie(self, media: MediaData) -> MediaData:
        tmdb_id = media.get("tmdb_id")
        if tmdb_id is None:
            self._logger.debug("Movie media lacks TMDb ID; returning without caching.")
            return media

        existing = self._accept_cached(self._cache.get_cached_by_tmdb_id(tmdb_id, MOVIE), MOVIE)
        if existing:
            self._logger.debug("Movie already cached by TMDb ID.")
            return existing

        return self._cache_or_return(media)

    def _persist_episode(self, media: MediaData) -> MediaData:
        tmdb_id = media.get("tmdb_id")
        tmdb_series_id = media.get("tmdb_series_id")
        season = media.get("season")
        episode = media.get("episode")

        if tmdb_series_id is None or season is None or episode is None:
            self._logger.info("Episode lacks its TMDb series ID, season or episode; returning without caching.")
            return media

        existing = self._accept_cached(self._cache.get_cached_tv_episode(tmdb_series_id, season, episode), TV)
        if existing:
            self._logger.debug("Episode already cached by series/season/episode.")
            return existing

        if tmdb_id is None:
            self._logger.info(
                f"No TMDb episode ID for S{season}E{episode} of series {tmdb_series_id}; returning without caching."
            )
            return media

        if tmdb_id == tmdb_series_id:
            self._logger.warning(
                f"Episode record carries its series ID {tmdb_series_id} as TMDb ID; returning without caching."
            )
            return media

        existing = self._accept_cached(self._cache.get_cached_by_tmdb_id(tmdb_id, TV), TV)
        if existing:
            self._logger.debug("Episode already cached by TMDb ID.")
            return existing

        return self._cache_or_return(media)

    def _accept_cached(self, cached: MediaData | None, media_type: str) -> MediaData | None:
        if cached is None or is_record_of_media_type(cached, media_type):
            return cached

        self._logger.warning(
            f"Discarded cache hit of another media type: identified {media_type!r}, cached row {cached.get('id')} "
            f"is {cached.get('media_type')!r} with TMDb ID {cached.get('tmdb_id')}."
        )
        return None

    def _cache_or_return(self, media: MediaData) -> MediaData:
        if not self._cache.is_cacheable(media):
            self._logger.debug("Media lacks a value the cache requires (title or year); returning without caching.")
            return media

        return self._cache.cache_data(media)

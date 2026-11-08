"""Entry point of identification: runs the pipeline for a request and caches what it identifies."""

from dataclasses import dataclass

from src.media_identifiers.constants import MOVIE, TV
from src.media_identifiers.media_type_helpers import is_movie, is_record_of_media_type, is_tv
from src.media_identifiers.pipeline import (
    DecidedBy,
    IdentificationOutcome,
    PipelineContext,
    PipelineController,
    build_pipeline,
)
from src.models.media_identification_request import MediaIdentificationRequest
from src.models.media_info import MediaData
from src.repositories.media_info_cache import MediaInfoCache
from src.utils import get_otel_log_handler

_logger = get_otel_log_handler("MediaIdentifier")


@dataclass(frozen=True)
class IdentificationResult:
    """The answer to one identification request.

    Attributes:
        media: The media record when the outcome is ``identified``, None otherwise.
        outcome: The verdict.
        decided_by: The step that settled the media type or the ``not_media`` verdict; None when unidentified.
        cache_hit: Whether a cache lookup ended the pipeline.
    """

    media: MediaData | None
    outcome: IdentificationOutcome
    decided_by: DecidedBy | None = None
    cache_hit: bool = False


class MediaIdentifier:
    """Identifies media from a file name or known metadata, using and filling the cache.

    Args:
        cache_repository: The media cache.
    """

    def __init__(self, cache_repository: MediaInfoCache) -> None:
        self._cache = cache_repository
        self._logger = _logger

    @_logger.trace("identify")
    def identify(self, request: MediaIdentificationRequest) -> IdentificationResult:
        """Run the identification pipeline.

        Returns:
            ``identified`` with the cached record, or with the TMDB-matched record (cached when it can be);
            ``not_media`` when the file is not a movie or TV release; ``unidentified`` when no step produced a TMDB
            match (logged at INFO with what each step concluded).

        Raises:
            UpstreamUnavailableError: If TMDB is unavailable, or OpenAI is unavailable and the run could not identify
                the media without it.
            PipelineExecutionError: If a pipeline step raises any other error.
            RuntimeError: If the cache cannot be read or written.
        """
        self._logger.debug(f"Starting identification: {request.to_logging_payload()!r}")

        context = PipelineContext(request, cache_repository=self._cache, logger=self._logger)
        handlers = build_pipeline(request)
        controller = PipelineController(handlers, logger=self._logger)
        result = controller.run(context)

        if result.cached is not None:
            self._logger.debug("Returning cached result from pipeline.")
            return IdentificationResult(result.cached, IdentificationOutcome.IDENTIFIED, result.decided_by, True)

        if result.outcome == IdentificationOutcome.NOT_MEDIA:
            return IdentificationResult(None, IdentificationOutcome.NOT_MEDIA, result.decided_by)

        media = result.media
        if media and self._is_matched_on_tmdb(media):
            return IdentificationResult(self._persist_media(media), IdentificationOutcome.IDENTIFIED, result.decided_by)

        if context.deferred_upstream_error is not None:
            raise context.deferred_upstream_error

        subject = request.file_path or request.to_logging_payload()
        self._logger.info(f"Unidentified {subject!r}; steps: {context.step_readings!r}")
        return IdentificationResult(None, IdentificationOutcome.UNIDENTIFIED)

    @staticmethod
    def _is_matched_on_tmdb(media: MediaData) -> bool:
        media_type = media.get("media_type")
        if is_movie(media_type):
            return media.get("tmdb_id") is not None
        if is_tv(media_type):
            return media.get("tmdb_series_id") is not None
        return False

    @_logger.trace("get_media_info_by_filename")
    def get_media_info_by_filename(self, file_path: str) -> IdentificationResult:
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
    ) -> IdentificationResult:
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

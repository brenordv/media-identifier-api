"""Assembles the ordered list of identification steps for a request."""

from src.media_identifiers.pipeline.base import PipelineHandler
from src.media_identifiers.pipeline.handlers import (
    CacheLookupHandler,
    GuessItIdentificationHandler,
    NimbleTriageHandler,
    OpenAIFallbackHandler,
    TMDBEpisodeDetailsHandler,
    TMDBIdentifyMovieHandler,
    TMDBIdentifySeriesHandler,
    TMDBMovieExternalIdsHandler,
    TMDBSeriesExternalIdsHandler,
)
from src.models.media_identification_request import MediaIdentificationRequest, RequestMode
from src.utils import get_otel_log_handler

_logger = get_otel_log_handler("PipelineBuilder")


@_logger.trace("build_pipeline")
def build_pipeline(request: MediaIdentificationRequest) -> list[PipelineHandler]:
    """Return the steps for a request.

    Filename requests run guessit, the Nimble triage and the OpenAI fallback around TMDB identification; metadata
    requests start with a cache lookup and go straight to TMDB. Both end with TMDB enrichment, with cache lookups in
    between.
    """
    if request.mode == RequestMode.FILENAME:
        handlers: list[PipelineHandler] = [
            GuessItIdentificationHandler(),
            CacheLookupHandler(label="post-guessit"),
            NimbleTriageHandler(),
            CacheLookupHandler(label="post-nimble"),
            OpenAIFallbackHandler(after_tmdb=False),
            CacheLookupHandler(label="post-openai"),
            TMDBIdentifyMovieHandler(),
            TMDBIdentifySeriesHandler(),
            OpenAIFallbackHandler(after_tmdb=True),
            CacheLookupHandler(label="post-openai-retry"),
            TMDBIdentifyMovieHandler(),
            TMDBIdentifySeriesHandler(),
        ]
    else:
        handlers = [
            CacheLookupHandler(label="metadata-seed"),
            TMDBIdentifyMovieHandler(),
            TMDBIdentifySeriesHandler(),
        ]

    handlers.extend(
        [
            CacheLookupHandler(label="post-tmdb-identify"),
            TMDBMovieExternalIdsHandler(),
            TMDBSeriesExternalIdsHandler(),
            TMDBEpisodeDetailsHandler(),
            CacheLookupHandler(label="post-tmdb-enrichment"),
        ]
    )

    return handlers

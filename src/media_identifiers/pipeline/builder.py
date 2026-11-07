"""Assembles the ordered list of identification steps for a request."""

from src.media_identifiers.pipeline.base import PipelineHandler
from src.media_identifiers.pipeline.handlers import (
    CacheLookupHandler,
    GuessItIdentificationHandler,
    OpenAIBasicIdentificationHandler,
    OpenAISeriesSeasonEpisodeHandler,
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

    Filename requests start with guessit and OpenAI identification; metadata requests start with a cache lookup.
    Both continue with TMDB identification and enrichment, with cache lookups in between.
    """
    handlers: list[PipelineHandler] = []

    if request.mode == RequestMode.FILENAME:
        handlers.extend(
            [
                GuessItIdentificationHandler(),
                CacheLookupHandler(label="post-guessit"),
                OpenAIBasicIdentificationHandler(),
                CacheLookupHandler(label="post-openai"),
            ]
        )
    else:
        handlers.append(CacheLookupHandler(label="metadata-seed"))

    handlers.extend(
        [
            TMDBIdentifyMovieHandler(),
            TMDBIdentifySeriesHandler(),
            CacheLookupHandler(label="post-tmdb-identify"),
            OpenAISeriesSeasonEpisodeHandler(),
            TMDBMovieExternalIdsHandler(),
            TMDBSeriesExternalIdsHandler(),
            TMDBEpisodeDetailsHandler(),
            CacheLookupHandler(label="post-tmdb-enrichment"),
        ]
    )

    return handlers

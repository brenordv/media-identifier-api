from typing import List

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


def build_pipeline(request: MediaIdentificationRequest) -> List[PipelineHandler]:
    handlers: List[PipelineHandler] = []

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



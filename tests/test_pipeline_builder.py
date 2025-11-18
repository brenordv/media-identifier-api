from src.media_identifiers.pipeline.builder import build_pipeline
from src.media_identifiers.pipeline.handlers import (
    CacheLookupHandler,
    GuessItIdentificationHandler,
    TMDBIdentifyMovieHandler,
    TMDBIdentifySeriesHandler,
)
from src.models.media_identification_request import MediaIdentificationRequest


def test_filename_pipeline_starts_with_guessit_and_cache():
    request = MediaIdentificationRequest.from_filename("Movie.Title.2024.1080p.mkv")

    handlers = build_pipeline(request)

    assert isinstance(handlers[0], GuessItIdentificationHandler)
    assert isinstance(handlers[1], CacheLookupHandler)
    assert any(isinstance(handler, TMDBIdentifyMovieHandler) for handler in handlers)
    assert any(isinstance(handler, TMDBIdentifySeriesHandler) for handler in handlers)


def test_metadata_pipeline_starts_with_cache_lookup():
    request = MediaIdentificationRequest.from_metadata(
        media_type="movie",
        title="Example Movie",
        year=2024,
    )

    handlers = build_pipeline(request)

    assert isinstance(handlers[0], CacheLookupHandler)
    assert any(isinstance(handler, TMDBIdentifyMovieHandler) for handler in handlers)



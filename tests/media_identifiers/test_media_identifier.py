import logging

import pytest

from src.media_identifiers import media_identifier as media_identifier_module
from src.media_identifiers.media_identifier import MediaIdentifier
from src.media_identifiers.pipeline import IdentificationOutcome, PipelineContext, PipelineHandler, StepResult
from src.media_identifiers.pipeline.handlers import CacheLookupHandler
from src.models.media_identification_request import MediaIdentificationRequest
from src.models.media_info import MediaData, MediaInfoBuilder
from tests.fakes import InMemoryCache

FILE_NAME = "Possessed.2000.1080p.BluRay.x264.mkv"


class MergeMediaStep(PipelineHandler):
    name = "merge_media"

    def __init__(self, media: MediaData) -> None:
        self._media = media

    def invoke(self, context: PipelineContext) -> StepResult:
        context.update_media(self._media)
        context.decided_by = "guessit"
        context.step_readings["merge_media"] = "merged"
        return StepResult.success()


class NotMediaStep(PipelineHandler):
    name = "not_media"

    def invoke(self, context: PipelineContext) -> StepResult:
        context.mark_not_media("nimble")
        return StepResult.done()


@pytest.fixture
def pipeline_yields(monkeypatch: pytest.MonkeyPatch) -> list[PipelineHandler]:
    steps: list[PipelineHandler] = []
    monkeypatch.setattr(media_identifier_module, "build_pipeline", lambda request: steps)
    return steps


def _movie(**overrides: object) -> MediaData:
    media = (
        MediaInfoBuilder()
        .with_title("Possessed")
        .with_original_title("Possessed")
        .with_media_type("movie")
        .with_tmdb_id(26620)
        .with_year(2000)
        .build()
    )
    return {**media, **overrides}


def _episode(**overrides: object) -> MediaData:
    media = (
        MediaInfoBuilder()
        .with_title("Slow Horses")
        .with_original_title("Slow Horses")
        .with_media_type("tv")
        .with_tmdb_id(6545154)
        .with_tmdb_series_id(95480)
        .with_season(6)
        .with_episode(6)
        .with_year(2026)
        .build()
    )
    return {**media, **overrides}


def test_identify_new_movie_is_cached_and_identified(pipeline_yields: list[PipelineHandler]) -> None:
    cache = InMemoryCache()
    pipeline_yields.append(MergeMediaStep(_movie()))

    result = MediaIdentifier(cache).get_media_info_by_filename(FILE_NAME)

    assert result.outcome == IdentificationOutcome.IDENTIFIED
    assert result.decided_by == "guessit"
    assert result.media is not None
    assert result.media["id"] == "cached-1"
    assert len(cache.inserted) == 1


def test_identify_movie_already_cached_by_tmdb_id_returns_the_cached_row(
    pipeline_yields: list[PipelineHandler],
) -> None:
    cached = _movie(id="existing")
    cache = InMemoryCache(records=[cached])
    pipeline_yields.append(MergeMediaStep(_movie()))

    result = MediaIdentifier(cache).get_media_info_by_filename(FILE_NAME)

    assert result.media == cached
    assert cache.inserted == []


def test_identify_movie_without_release_year_returns_it_uncached(pipeline_yields: list[PipelineHandler]) -> None:
    cache = InMemoryCache()
    pipeline_yields.append(MergeMediaStep(_movie(year=None)))

    result = MediaIdentifier(cache).get_media_info_by_filename(FILE_NAME)

    assert result.outcome == IdentificationOutcome.IDENTIFIED
    assert result.media is not None
    assert result.media["id"] is None
    assert cache.inserted == []


@pytest.mark.parametrize(
    "media",
    [_movie(tmdb_id=None), _movie(media_type="unknown"), _episode(tmdb_series_id=None)],
    ids=["movie without TMDB id", "unknown media type", "episode without series id"],
)
def test_identify_without_a_tmdb_match_is_unidentified_and_logged_with_the_step_readings(
    pipeline_yields: list[PipelineHandler], caplog: pytest.LogCaptureFixture, media: MediaData
) -> None:
    cache = InMemoryCache()
    pipeline_yields.append(MergeMediaStep(media))

    with caplog.at_level(logging.INFO):
        result = MediaIdentifier(cache).get_media_info_by_filename(FILE_NAME)

    assert (result.media, result.outcome, result.decided_by) == (None, IdentificationOutcome.UNIDENTIFIED, None)
    assert cache.inserted == []
    assert any(
        record.levelno == logging.INFO
        and f"Unidentified {FILE_NAME!r}" in record.getMessage()
        and "merged" in record.getMessage()
        for record in caplog.records
    )


def test_identify_not_media_persists_nothing(pipeline_yields: list[PipelineHandler]) -> None:
    cache = InMemoryCache()
    pipeline_yields.extend([MergeMediaStep(_movie()), NotMediaStep()])

    result = MediaIdentifier(cache).get_media_info_by_filename(FILE_NAME)

    assert (result.media, result.outcome, result.decided_by) == (None, IdentificationOutcome.NOT_MEDIA, "nimble")
    assert cache.inserted == []


def test_identify_episode_keyed_by_its_series_id_is_not_cached(
    pipeline_yields: list[PipelineHandler], caplog: pytest.LogCaptureFixture
) -> None:
    cache = InMemoryCache()
    pipeline_yields.append(MergeMediaStep(_episode(tmdb_id=95480)))

    with caplog.at_level(logging.WARNING):
        result = MediaIdentifier(cache).get_media_info_by_filename(FILE_NAME)

    assert result.outcome == IdentificationOutcome.IDENTIFIED
    assert cache.inserted == []
    assert any(
        record.levelno == logging.WARNING and "carries its series ID 95480" in record.getMessage()
        for record in caplog.records
    )


def test_identify_new_episode_is_cached(pipeline_yields: list[PipelineHandler]) -> None:
    cache = InMemoryCache()
    pipeline_yields.append(MergeMediaStep(_episode()))

    result = MediaIdentifier(cache).get_media_info_by_filename(FILE_NAME)

    assert result.media is not None
    assert result.media["id"] == "cached-1"
    assert cache.inserted[0]["tmdb_id"] == 6545154


def test_identify_metadata_request_records_the_request_as_the_decider(
    pipeline_yields: list[PipelineHandler],
) -> None:
    cache = InMemoryCache(records=[_movie(id="existing")])
    pipeline_yields.append(CacheLookupHandler(label="metadata-seed"))
    request = MediaIdentificationRequest.from_metadata(media_type="movie", year=2000, title="Possessed")

    result = MediaIdentifier(cache).identify(request)

    assert (result.outcome, result.decided_by, result.cache_hit) == (IdentificationOutcome.IDENTIFIED, "request", True)

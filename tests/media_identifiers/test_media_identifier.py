import pytest

from src.media_identifiers import media_identifier as media_identifier_module
from src.media_identifiers.media_identifier import MediaIdentifier
from src.media_identifiers.pipeline import PipelineContext, PipelineHandler, StepResult
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
        return StepResult.success()


@pytest.fixture
def pipeline_yields(monkeypatch: pytest.MonkeyPatch) -> list[MediaData]:
    produced: list[MediaData] = []

    def build(request: MediaIdentificationRequest) -> list[PipelineHandler]:
        return [MergeMediaStep(media) for media in produced]

    monkeypatch.setattr(media_identifier_module, "build_pipeline", build)
    return produced


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


def test_identify_new_movie_is_cached(pipeline_yields: list[MediaData]) -> None:
    cache = InMemoryCache()
    pipeline_yields.append(_movie())

    result = MediaIdentifier(cache).get_media_info_by_filename(FILE_NAME)

    assert result is not None
    assert result["id"] == "cached-1"
    assert len(cache.inserted) == 1


def test_identify_movie_already_cached_by_tmdb_id_returns_the_cached_row(pipeline_yields: list[MediaData]) -> None:
    cached = _movie(id="existing")
    cache = InMemoryCache(records=[cached])
    pipeline_yields.append(_movie())

    result = MediaIdentifier(cache).get_media_info_by_filename(FILE_NAME)

    assert result == cached
    assert cache.inserted == []


def test_identify_movie_without_release_year_returns_it_uncached(pipeline_yields: list[MediaData]) -> None:
    cache = InMemoryCache()
    pipeline_yields.append(_movie(year=None))

    result = MediaIdentifier(cache).get_media_info_by_filename(FILE_NAME)

    assert result is not None
    assert result["title"] == "Possessed"
    assert result["id"] is None
    assert cache.inserted == []


def test_identify_movie_without_tmdb_id_returns_it_uncached(pipeline_yields: list[MediaData]) -> None:
    cache = InMemoryCache()
    pipeline_yields.append(_movie(tmdb_id=None))

    result = MediaIdentifier(cache).get_media_info_by_filename(FILE_NAME)

    assert result is not None
    assert cache.inserted == []


def test_identify_unknown_media_type_returns_none(pipeline_yields: list[MediaData]) -> None:
    cache = InMemoryCache()
    pipeline_yields.append(_movie(media_type="unknown"))

    assert MediaIdentifier(cache).get_media_info_by_filename(FILE_NAME) is None

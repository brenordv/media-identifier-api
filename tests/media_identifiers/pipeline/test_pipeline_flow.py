import logging
from typing import Any

import pytest

from src.media_identifiers import tmdb_identifier
from src.media_identifiers.media_identifier import MediaIdentifier
from src.media_identifiers.pipeline.base import PipelineExecutionError
from src.models.media_info import MediaData
from tests.fakes import InMemoryCache

SLOW_HORSES_FILE = "/watch/Slow.Horses.S06E06.Judgment.Day.1080p.ATVP.WEB-DL.DDP5.1.H.264-NTb.mkv"
POSSESSED_FILE = "Possessed.2000.1080p.BluRay.x264.mkv"
SERIES_ID = 95480
EPISODE_ID = 6545154
MOVIE_ID = 26620

FLESH_TX_ROW: MediaData = {
    "id": "488f5580-989c-4a4e-a9e2-5b0c154fd0ce",
    "tmdb_id": SERIES_ID,
    "tmdb_series_id": None,
    "title": "Flesh, TX",
    "original_title": "Flesh, TX",
    "media_type": "movie",
    "year": 2009,
    "season": None,
    "episode": None,
}

TMDB_RESPONSES: dict[str, dict[str, Any]] = {
    "/search/tv": {
        "results": [
            {
                "id": SERIES_ID,
                "name": "Slow Horses",
                "original_name": "Slow Horses",
                "first_air_date": "2022-04-01",
                "genre_ids": [18, 80],
                "original_language": "en",
            }
        ]
    },
    f"/tv/{SERIES_ID}": {
        "id": SERIES_ID,
        "name": "Slow Horses",
        "original_name": "Slow Horses",
        "first_air_date": "2022-04-01",
    },
    f"/tv/{SERIES_ID}/external_ids": {"imdb_id": "tt5875444", "tvdb_id": 371713},
    f"/tv/{SERIES_ID}/season/6/episode/6": {
        "id": EPISODE_ID,
        "name": "Judgment Day",
        "season_number": 6,
        "episode_number": 6,
        "air_date": "2026-10-29",
        "overview": "The season finale.",
    },
    "/search/movie": {
        "results": [{"id": MOVIE_ID, "title": "Possessed", "original_title": "Possessed", "release_date": "2000-10-31"}]
    },
    f"/movie/{MOVIE_ID}": {
        "id": MOVIE_ID,
        "title": "Possessed",
        "original_title": "Possessed",
        "release_date": "2000-10-31",
    },
    f"/movie/{MOVIE_ID}/external_ids": {"imdb_id": "tt0195165"},
}


@pytest.fixture
def tmdb(monkeypatch: pytest.MonkeyPatch) -> dict[str, dict[str, Any]]:
    responses = dict(TMDB_RESPONSES)

    def fake_make_request(url: str, params: dict[str, Any] | None = None) -> dict[str, Any] | None:
        return responses.get(url.removeprefix(tmdb_identifier.TMDB_API_BASE_URL))

    monkeypatch.setattr(tmdb_identifier, "_make_request", fake_make_request)
    return responses


@pytest.mark.usefixtures("tmdb")
def test_slow_horses_episode_is_never_answered_with_the_movie_sharing_its_tmdb_id() -> None:
    cache = InMemoryCache(records=[FLESH_TX_ROW])

    result = MediaIdentifier(cache).get_media_info_by_filename(SLOW_HORSES_FILE.lower())

    assert result is not None
    assert result["media_type"] == "tv"
    assert result["title"] == "Slow Horses"
    assert (result["season"], result["episode"]) == (6, 6)
    assert result["tmdb_id"] == EPISODE_ID
    assert result["tmdb_series_id"] == SERIES_ID
    assert result["episode_title"] == "Judgment Day"
    assert result["imdb_id"] == "tt5875444"
    assert result["year"] == 2026
    assert cache.inserted == [result]


@pytest.mark.usefixtures("tmdb")
def test_cache_hits_of_another_media_type_are_discarded(caplog: pytest.LogCaptureFixture) -> None:
    movie_named_like_the_show = {
        **FLESH_TX_ROW,
        "id": "same-title-movie",
        "title": "slow horses",
        "tmdb_id": 1,
        "season": 6,
        "episode": 6,
    }
    movie_with_the_series_numbers = {
        **FLESH_TX_ROW,
        "id": "movie-with-series-numbers",
        "title": "Unrelated Movie",
        "tmdb_id": 2,
        "tmdb_series_id": SERIES_ID,
        "season": 6,
        "episode": 6,
    }
    flesh_tx_with_the_episode_id = {**FLESH_TX_ROW, "id": "movie-with-episode-id", "tmdb_id": EPISODE_ID}
    cache = InMemoryCache(
        records=[movie_named_like_the_show, movie_with_the_series_numbers, flesh_tx_with_the_episode_id],
        ignore_media_type=True,
    )

    with caplog.at_level(logging.WARNING):
        result = MediaIdentifier(cache).get_media_info_by_filename(SLOW_HORSES_FILE.lower())

    assert result is not None
    assert result["media_type"] == "tv"
    assert result["tmdb_id"] == EPISODE_ID
    discarded_rows = {
        row_id
        for record in caplog.records
        if "Discarded cache hit of another media type" in record.getMessage()
        for row_id in ("same-title-movie", "movie-with-series-numbers", "movie-with-episode-id")
        if f"cached row {row_id} " in record.getMessage()
    }
    assert discarded_rows == {"same-title-movie", "movie-with-series-numbers", "movie-with-episode-id"}


def test_episode_tmdb_does_not_list_yet_is_returned_uncached(
    tmdb: dict[str, dict[str, Any]], caplog: pytest.LogCaptureFixture
) -> None:
    del tmdb[f"/tv/{SERIES_ID}/season/6/episode/6"]
    cache = InMemoryCache()

    with caplog.at_level(logging.INFO):
        result = MediaIdentifier(cache).get_media_info_by_filename(SLOW_HORSES_FILE)

    assert result is not None
    assert result["media_type"] == "tv"
    assert result["tmdb_id"] is None
    assert result["tmdb_series_id"] == SERIES_ID
    assert cache.inserted == []
    assert any(
        record.levelno == logging.INFO and "No TMDb episode ID for S6E6" in record.getMessage()
        for record in caplog.records
    )


@pytest.mark.usefixtures("tmdb")
def test_cached_episode_is_returned_by_series_season_and_episode() -> None:
    cached_episode = {
        **FLESH_TX_ROW,
        "id": "cached-episode",
        "title": "Slow Horses (cached under another title)",
        "media_type": "tv",
        "tmdb_id": EPISODE_ID,
        "tmdb_series_id": SERIES_ID,
        "season": 6,
        "episode": 6,
        "year": 2026,
    }
    cache = InMemoryCache(records=[cached_episode])

    result = MediaIdentifier(cache).get_media_info_by_filename(SLOW_HORSES_FILE)

    assert result == cached_episode
    assert cache.inserted == []


def test_special_episode_in_season_zero_is_identified(tmdb: dict[str, dict[str, Any]]) -> None:
    tmdb[f"/tv/{SERIES_ID}/season/0/episode/1"] = {
        "id": 3000001,
        "name": "Behind the Scenes",
        "season_number": 0,
        "episode_number": 1,
        "air_date": "2022-03-01",
    }

    result = MediaIdentifier(InMemoryCache()).get_media_info_by_filename(
        "Slow.Horses.S00E01.1080p.ATVP.WEB-DL.DDP5.1.H.264-NTb.mkv"
    )

    assert result is not None
    assert (result["season"], result["episode"]) == (0, 1)
    assert result["tmdb_id"] == 3000001
    assert result["episode_title"] == "Behind the Scenes"


@pytest.mark.usefixtures("tmdb")
def test_movie_is_identified_enriched_and_cached_next_to_an_episode_with_the_same_id() -> None:
    episode_with_the_movie_id = {
        **FLESH_TX_ROW,
        "id": "episode-26620",
        "title": "Some Show",
        "media_type": "tv",
        "tmdb_id": MOVIE_ID,
        "tmdb_series_id": 1,
        "season": 1,
        "episode": 1,
    }
    cache = InMemoryCache(records=[episode_with_the_movie_id])

    result = MediaIdentifier(cache).get_media_info_by_filename(POSSESSED_FILE)

    assert result is not None
    assert result["media_type"] == "movie"
    assert result["title"] == "Possessed"
    assert result["tmdb_id"] == MOVIE_ID
    assert result["imdb_id"] == "tt0195165"
    assert cache.inserted == [result]


@pytest.mark.usefixtures("tmdb")
def test_media_info_by_metadata_identifies_the_episode() -> None:
    cache = InMemoryCache(records=[FLESH_TX_ROW])

    result = MediaIdentifier(cache).get_media_info(media_type="tv", year=2022, title="Slow Horses", season=6, episode=6)

    assert result is not None
    assert result["media_type"] == "tv"
    assert result["tmdb_id"] == EPISODE_ID


def test_series_unknown_to_tmdb_fails_the_pipeline(tmdb: dict[str, dict[str, Any]]) -> None:
    tmdb["/search/tv"] = {"results": []}

    with pytest.raises(PipelineExecutionError):
        MediaIdentifier(InMemoryCache()).get_media_info_by_filename(SLOW_HORSES_FILE)

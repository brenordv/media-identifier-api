import logging
from typing import Any

import pytest

from src.converters.create_searchable_reference import create_searchable_reference
from src.media_identifiers import tmdb_identifier
from src.media_identifiers.errors import UpstreamUnavailableError
from src.media_identifiers.media_identifier import MediaIdentifier
from src.media_identifiers.nimble_classifier import NimbleChoice, NimbleVerdict
from src.media_identifiers.openai_identifier import OpenAIIdentification, OpenAIMediaGuess
from src.media_identifiers.pipeline import IdentificationOutcome, handlers
from src.models.media_info import MediaData, MediaInfoBuilder
from tests.fakes import InMemoryCache

SLOW_HORSES_FILE = "/watch/Slow.Horses.S06E06.Judgment.Day.1080p.ATVP.WEB-DL.DDP5.1.H.264-NTb.mkv"
POSSESSED_FILE = "Possessed.2000.1080p.BluRay.x264.mkv"
PULSE_FILE = "Pulse.2.Afterlife.2008.1080p.BluRay.x264-GUACAMOLE/gua-pulse2.2008-1080p.mkv"
ROM_FILE = "/watch/Retro/NES/Balloon Fight (JU) [o5].nes"
SERIES_ID = 95480
EPISODE_ID = 6545154
MOVIE_ID = 26620
PULSE_ID = 14212

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

TMDB_RESPONSES: dict[str, Any] = {
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
    "/search/movie?query=Pulse 2: Afterlife": {
        "results": [{"id": PULSE_ID, "title": "Pulse 2: Afterlife", "release_date": "2008-09-30"}]
    },
    f"/movie/{PULSE_ID}": {
        "id": PULSE_ID,
        "title": "Pulse 2: Afterlife",
        "original_title": "Pulse 2: Afterlife",
        "release_date": "2008-09-30",
    },
    f"/movie/{PULSE_ID}/external_ids": {"imdb_id": "tt1114713"},
}


class FakeTmdb:
    """Answers TMDB requests from a table keyed by path, or by search path plus query (and year); records calls."""

    def __init__(self, responses: dict[str, Any]) -> None:
        self.responses = responses
        self.calls: list[tuple[str, dict[str, Any] | None]] = []

    def __call__(self, url: str, params: dict[str, Any] | None = None) -> dict[str, Any] | None:
        path = url.removeprefix(tmdb_identifier.TMDB_API_BASE_URL)
        self.calls.append((path, params))
        keys = [path]
        if params and "query" in params:
            query = params["query"]
            keys = [f"{path}?query={query}&year={params.get('year')}", f"{path}?query={query}", path]
        for key in keys:
            if key in self.responses:
                value = self.responses[key]
                if isinstance(value, Exception):
                    raise value
                return dict(value)
        return None

    @property
    def searches(self) -> list[dict[str, Any] | None]:
        return [params for path, params in self.calls if path.startswith("/search/")]


class FakeOpenAI:
    """Stands in for the OpenAI call: returns queued identifications or raises, and records the hints it got."""

    def __init__(self, *answers: OpenAIIdentification | Exception) -> None:
        self._answers = list(answers)
        self.calls: list[dict[str, Any]] = []

    def __call__(self, file_path: str, hints: dict[str, Any]) -> OpenAIIdentification:
        self.calls.append(hints)
        answer = self._answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return answer


def _answered(**fields: Any) -> OpenAIIdentification:
    values: dict[str, Any] = {"media_type": "movie", "title": None, "year": None, "season": None, "episode": None}
    return OpenAIIdentification("answered", OpenAIMediaGuess(**(values | fields)))


@pytest.fixture
def tmdb(monkeypatch: pytest.MonkeyPatch) -> FakeTmdb:
    fake = FakeTmdb(dict(TMDB_RESPONSES))
    monkeypatch.setattr(tmdb_identifier, "_make_request", fake)
    return fake


@pytest.fixture
def openai(monkeypatch: pytest.MonkeyPatch) -> FakeOpenAI:
    fake = FakeOpenAI()
    monkeypatch.setattr(handlers, "identify_media_with_openai", fake)
    monkeypatch.setattr(handlers, "is_openai_configured", lambda: True)
    return fake


def nimble_says(monkeypatch: pytest.MonkeyPatch, choice: NimbleChoice | None, confidence: float = 0.95) -> None:
    verdict = NimbleVerdict(choice, confidence) if choice else None
    monkeypatch.setattr(handlers, "classify_media_kind", lambda file_path: verdict)


def guessit_reads(monkeypatch: pytest.MonkeyPatch, **fields: Any) -> None:
    builder = MediaInfoBuilder().with_used_guessit(True)
    title = fields.get("title")
    media: MediaData = {
        **builder.build(),
        **fields,
        "searchable_reference": create_searchable_reference(title) if title else None,
    }
    monkeypatch.setattr(handlers, "identify_media_with_guess_it", lambda file_path: dict(media))


@pytest.mark.usefixtures("tmdb")
def test_slow_horses_episode_is_never_answered_with_the_movie_sharing_its_tmdb_id() -> None:
    cache = InMemoryCache(records=[FLESH_TX_ROW])

    result = MediaIdentifier(cache).get_media_info_by_filename(SLOW_HORSES_FILE.lower())

    media = result.media
    assert media is not None
    assert media["media_type"] == "tv"
    assert media["title"] == "Slow Horses"
    assert (media["season"], media["episode"]) == (6, 6)
    assert media["tmdb_id"] == EPISODE_ID
    assert media["tmdb_series_id"] == SERIES_ID
    assert media["episode_title"] == "Judgment Day"
    assert media["imdb_id"] == "tt5875444"
    assert media["year"] == 2026
    assert cache.inserted == [media]
    assert (result.outcome, result.decided_by) == (IdentificationOutcome.IDENTIFIED, "guessit")


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

    assert result.media is not None
    assert result.media["media_type"] == "tv"
    assert result.media["tmdb_id"] == EPISODE_ID
    discarded_rows = {
        row_id
        for record in caplog.records
        if "Discarded cache hit of another media type" in record.getMessage()
        for row_id in ("same-title-movie", "movie-with-series-numbers", "movie-with-episode-id")
        if f"cached row {row_id} " in record.getMessage()
    }
    assert discarded_rows == {"same-title-movie", "movie-with-series-numbers", "movie-with-episode-id"}


def test_episode_tmdb_does_not_list_yet_is_identified_and_returned_uncached(
    tmdb: FakeTmdb, caplog: pytest.LogCaptureFixture
) -> None:
    del tmdb.responses[f"/tv/{SERIES_ID}/season/6/episode/6"]
    cache = InMemoryCache()

    with caplog.at_level(logging.INFO):
        result = MediaIdentifier(cache).get_media_info_by_filename(SLOW_HORSES_FILE)

    assert result.outcome == IdentificationOutcome.IDENTIFIED
    assert result.media is not None
    assert result.media["tmdb_id"] is None
    assert result.media["tmdb_series_id"] == SERIES_ID
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

    assert result.media == cached_episode
    assert cache.inserted == []


def test_special_episode_in_season_zero_is_identified(tmdb: FakeTmdb) -> None:
    tmdb.responses[f"/tv/{SERIES_ID}/season/0/episode/1"] = {
        "id": 3000001,
        "name": "Behind the Scenes",
        "season_number": 0,
        "episode_number": 1,
        "air_date": "2022-03-01",
    }

    result = MediaIdentifier(InMemoryCache()).get_media_info_by_filename(
        "Slow.Horses.S00E01.1080p.ATVP.WEB-DL.DDP5.1.H.264-NTb.mkv"
    )

    assert result.media is not None
    assert (result.media["season"], result.media["episode"]) == (0, 1)
    assert result.media["tmdb_id"] == 3000001
    assert result.media["episode_title"] == "Behind the Scenes"


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

    assert result.media is not None
    assert result.media["media_type"] == "movie"
    assert result.media["title"] == "Possessed"
    assert result.media["tmdb_id"] == MOVIE_ID
    assert result.media["imdb_id"] == "tt0195165"
    assert cache.inserted == [result.media]


@pytest.mark.usefixtures("tmdb")
def test_media_info_by_metadata_identifies_the_episode() -> None:
    cache = InMemoryCache(records=[FLESH_TX_ROW])

    result = MediaIdentifier(cache).get_media_info(media_type="tv", year=2022, title="Slow Horses", season=6, episode=6)

    assert result.media is not None
    assert result.media["tmdb_id"] == EPISODE_ID
    assert result.decided_by == "request"


def test_series_unknown_to_tmdb_is_unidentified_without_openai(tmdb: FakeTmdb) -> None:
    tmdb.responses["/search/tv"] = {"results": []}

    result = MediaIdentifier(InMemoryCache()).get_media_info_by_filename(SLOW_HORSES_FILE)

    assert (result.media, result.outcome, result.decided_by) == (None, IdentificationOutcome.UNIDENTIFIED, None)


def test_rom_rejected_by_nimble_is_not_media_without_tmdb_or_openai(
    monkeypatch: pytest.MonkeyPatch, tmdb: FakeTmdb, openai: FakeOpenAI
) -> None:
    nimble_says(monkeypatch, "other", 1.0)
    cache = InMemoryCache()

    result = MediaIdentifier(cache).get_media_info_by_filename(ROM_FILE)

    assert (result.media, result.outcome, result.decided_by) == (None, IdentificationOutcome.NOT_MEDIA, "nimble")
    assert tmdb.calls == []
    assert openai.calls == []
    assert cache.inserted == []


def test_confident_nimble_overrides_guessit_and_marks_the_cached_record(
    monkeypatch: pytest.MonkeyPatch, tmdb: FakeTmdb
) -> None:
    guessit_reads(monkeypatch, title="Possessed", media_type="tv", year=2000)
    nimble_says(monkeypatch, "movie", 0.9)
    cache = InMemoryCache()

    result = MediaIdentifier(cache).get_media_info_by_filename(POSSESSED_FILE)

    assert result.decided_by == "nimble"
    assert cache.inserted[0]["tmdb_id"] == MOVIE_ID
    assert cache.inserted[0]["used_nimble"] is True


def test_openai_overriding_nimble_clears_used_nimble(
    monkeypatch: pytest.MonkeyPatch, tmdb: FakeTmdb, openai: FakeOpenAI
) -> None:
    guessit_reads(monkeypatch, title="slow horses", media_type="tv", season=6, episode=6)
    nimble_says(monkeypatch, "movie", 0.9)
    tmdb.responses["/search/movie"] = {"results": []}
    openai._answers.append(_answered(media_type="tv", title="Slow Horses", season=6, episode=6))
    cache = InMemoryCache()

    result = MediaIdentifier(cache).get_media_info_by_filename(SLOW_HORSES_FILE)

    assert openai.calls[0]["trigger"] == "tmdb_no_match"
    assert result.decided_by == "openai"
    assert cache.inserted[0]["tmdb_id"] == EPISODE_ID
    assert (cache.inserted[0]["used_nimble"], cache.inserted[0]["used_openai"]) == (False, True)


def test_unsure_nimble_disagreeing_with_guessit_asks_openai_once(
    monkeypatch: pytest.MonkeyPatch, tmdb: FakeTmdb, openai: FakeOpenAI
) -> None:
    guessit_reads(monkeypatch, title="Possessed", media_type="movie", year=2000)
    nimble_says(monkeypatch, "tv", 0.5)
    openai._answers.append(_answered(title=None, year=2000))

    result = MediaIdentifier(InMemoryCache()).get_media_info_by_filename(POSSESSED_FILE)

    assert [call["trigger"] for call in openai.calls] == ["type_uncertain"]
    assert openai.calls[0]["nimble"] == {"choice": "tv", "confidence": 0.5}
    assert openai.calls[0]["guessit"]["title"] == "Possessed"
    assert result.media is not None
    assert result.media["title"] == "Possessed"
    assert result.decided_by == "guessit"


def test_tmdb_no_match_is_retried_with_the_openai_title_and_cached_under_it(
    monkeypatch: pytest.MonkeyPatch, tmdb: FakeTmdb, openai: FakeOpenAI
) -> None:
    guessit_reads(monkeypatch, title="gua pulse2", media_type="movie", year=2008)
    tmdb.responses["/search/movie"] = {"results": []}
    openai._answers.append(_answered(title="Pulse 2: Afterlife", year=2008))
    cache = InMemoryCache()

    result = MediaIdentifier(cache).get_media_info_by_filename(PULSE_FILE)

    assert openai.calls[0]["searched"] == {"title": "gua pulse2", "year": 2008}
    assert [params["query"] for params in tmdb.searches if params] == ["gua pulse2", "Pulse 2: Afterlife"]
    assert result.media is not None
    assert result.media["tmdb_id"] == PULSE_ID
    assert cache.inserted[0]["searchable_reference"] == create_searchable_reference("Pulse 2: Afterlife")
    guessit_reading = {
        "title": "gua pulse2",
        "media_type": "movie",
        "year": 2008,
        "searchable_reference": create_searchable_reference("gua pulse2"),
    }
    assert cache.get_cached_by_obj(guessit_reading) is None


def test_openai_title_that_tmdb_matches_to_another_title_ends_unidentified(
    monkeypatch: pytest.MonkeyPatch, tmdb: FakeTmdb, openai: FakeOpenAI
) -> None:
    guessit_reads(monkeypatch, title="zxqv blorptastic quantum", media_type="movie", year=2019)
    tmdb.responses["/search/movie"] = {"results": []}
    tmdb.responses["/search/movie?query=Quantum"] = {
        "results": [{"id": 819189, "title": "Marit Voldsaeter: Null i biologi", "release_date": "2019-03-01"}]
    }
    tmdb.responses["/movie/819189"] = {
        "id": 819189,
        "title": "Marit Voldsaeter: Null i biologi",
        "original_title": "Marit Voldsaeter: Null i biologi",
        "release_date": "2019-03-01",
    }
    openai._answers.append(_answered(title="Quantum", year=2019))
    cache = InMemoryCache()

    result = MediaIdentifier(cache).get_media_info_by_filename("Zxqv.Blorptastic.Quantum.2019.1080p.WEB-DL.mkv")

    assert [params["query"] for params in tmdb.searches if params] == ["zxqv blorptastic quantum", "Quantum"]
    assert result.outcome == IdentificationOutcome.UNIDENTIFIED
    assert cache.inserted == []


def test_openai_clearing_a_wrong_year_searches_without_it(
    monkeypatch: pytest.MonkeyPatch, tmdb: FakeTmdb, openai: FakeOpenAI
) -> None:
    guessit_reads(monkeypatch, title="Pulse 2: Afterlife", media_type="movie", year=2009)
    tmdb.responses["/search/movie"] = {"results": []}
    tmdb.responses["/search/movie?query=Pulse 2: Afterlife&year=2009"] = {"results": []}
    openai._answers.append(_answered(title="Pulse 2: Afterlife", year=None))

    result = MediaIdentifier(InMemoryCache()).get_media_info_by_filename(PULSE_FILE)

    assert [params.get("year") for params in tmdb.searches if params] == [2009, None]
    assert result.outcome == IdentificationOutcome.IDENTIFIED


def test_openai_repeating_the_searched_title_does_not_search_again_and_ends_unidentified(
    monkeypatch: pytest.MonkeyPatch, tmdb: FakeTmdb, openai: FakeOpenAI, caplog: pytest.LogCaptureFixture
) -> None:
    guessit_reads(monkeypatch, title="Unknown Thing", media_type="movie", year=2001)
    tmdb.responses["/search/movie"] = {"results": []}
    openai._answers.append(_answered(title="unknown thing", year=2001))

    with caplog.at_level(logging.INFO):
        result = MediaIdentifier(InMemoryCache()).get_media_info_by_filename("Unknown.Thing.2001.mkv")

    assert len(tmdb.searches) == 1
    assert (result.outcome, result.decided_by) == (IdentificationOutcome.UNIDENTIFIED, None)
    assert any("Unidentified" in record.getMessage() and "openai" in record.getMessage() for record in caplog.records)


def test_openai_refusing_after_a_tmdb_miss_ends_unidentified(
    monkeypatch: pytest.MonkeyPatch, tmdb: FakeTmdb, openai: FakeOpenAI
) -> None:
    guessit_reads(monkeypatch, title="Unknown Thing", media_type="movie", year=2001)
    tmdb.responses["/search/movie"] = {"results": []}
    openai._answers.append(OpenAIIdentification("refused"))

    result = MediaIdentifier(InMemoryCache()).get_media_info_by_filename("Unknown.Thing.2001.mkv")

    assert result.outcome == IdentificationOutcome.UNIDENTIFIED
    assert len(openai.calls) == 1


def test_openai_saying_other_is_not_media(monkeypatch: pytest.MonkeyPatch, tmdb: FakeTmdb, openai: FakeOpenAI) -> None:
    guessit_reads(monkeypatch, title="logo", media_type=None)
    openai._answers.append(_answered(media_type="other"))

    result = MediaIdentifier(InMemoryCache()).get_media_info_by_filename("logo.png")

    assert (result.outcome, result.decided_by) == (IdentificationOutcome.NOT_MEDIA, "openai")
    assert openai.calls[0]["trigger"] == "type_uncertain"
    assert tmdb.calls == []


def test_nimble_without_a_verdict_leaves_the_decision_to_guessit(
    monkeypatch: pytest.MonkeyPatch, tmdb: FakeTmdb, openai: FakeOpenAI
) -> None:
    nimble_says(monkeypatch, None)

    result = MediaIdentifier(InMemoryCache()).get_media_info_by_filename(POSSESSED_FILE)

    assert (result.outcome, result.decided_by) == (IdentificationOutcome.IDENTIFIED, "guessit")
    assert openai.calls == []


def test_openai_title_null_keeps_the_guessit_title(
    monkeypatch: pytest.MonkeyPatch, tmdb: FakeTmdb, openai: FakeOpenAI
) -> None:
    guessit_reads(monkeypatch, title="Possessed", media_type="tv", year=2000)
    nimble_says(monkeypatch, "movie", 0.5)
    openai._answers.append(_answered(title=None, year=2000))

    result = MediaIdentifier(InMemoryCache()).get_media_info_by_filename(POSSESSED_FILE)

    assert result.media is not None
    assert result.media["tmdb_id"] == MOVIE_ID
    assert tmdb.searches[0] is not None
    assert tmdb.searches[0]["query"] == "Possessed"


def test_titleless_media_never_reaches_a_tmdb_search(monkeypatch: pytest.MonkeyPatch, tmdb: FakeTmdb) -> None:
    guessit_reads(monkeypatch, title=None, media_type="movie", year=2000)

    result = MediaIdentifier(InMemoryCache()).get_media_info_by_filename("2000.mkv")

    assert result.outcome == IdentificationOutcome.UNIDENTIFIED
    assert tmdb.calls == []


def test_openai_is_asked_at_most_once_per_run(
    monkeypatch: pytest.MonkeyPatch, tmdb: FakeTmdb, openai: FakeOpenAI
) -> None:
    guessit_reads(monkeypatch, title="Unknown Thing", media_type="movie", year=2001)
    nimble_says(monkeypatch, "tv", 0.5)
    tmdb.responses["/search/movie"] = {"results": []}
    openai._answers.append(_answered(title="Another Unknown Thing", year=2001))

    result = MediaIdentifier(InMemoryCache()).get_media_info_by_filename("Unknown.Thing.2001.mkv")

    assert [call["trigger"] for call in openai.calls] == ["type_uncertain"]
    assert result.outcome == IdentificationOutcome.UNIDENTIFIED


def test_tmdb_unavailable_during_identification_propagates_unwrapped(tmdb: FakeTmdb) -> None:
    tmdb.responses["/search/movie"] = UpstreamUnavailableError("tmdb", "timeout")

    with pytest.raises(UpstreamUnavailableError):
        MediaIdentifier(InMemoryCache()).get_media_info_by_filename(POSSESSED_FILE)


def test_tmdb_unavailable_during_enrichment_propagates_and_caches_nothing(tmdb: FakeTmdb) -> None:
    tmdb.responses[f"/movie/{MOVIE_ID}/external_ids"] = UpstreamUnavailableError("tmdb", "server_error")
    cache = InMemoryCache()

    with pytest.raises(UpstreamUnavailableError):
        MediaIdentifier(cache).get_media_info_by_filename(POSSESSED_FILE)

    assert cache.inserted == []


def test_openai_unavailable_when_needed_propagates(
    monkeypatch: pytest.MonkeyPatch, tmdb: FakeTmdb, openai: FakeOpenAI
) -> None:
    guessit_reads(monkeypatch, title=None, media_type="movie")
    openai._answers.append(UpstreamUnavailableError("openai", "rate_limited", "credit_balance_exhausted"))

    with pytest.raises(UpstreamUnavailableError):
        MediaIdentifier(InMemoryCache()).get_media_info_by_filename("mystery.mkv")

    assert openai.calls[0]["trigger"] == "no_title"


def test_openai_unavailable_with_a_searchable_reading_still_identifies_through_tmdb(
    monkeypatch: pytest.MonkeyPatch, tmdb: FakeTmdb, openai: FakeOpenAI, caplog: pytest.LogCaptureFixture
) -> None:
    guessit_reads(monkeypatch, title="Slow Horses", media_type="tv")
    openai._answers.append(UpstreamUnavailableError("openai", "timeout"))

    with caplog.at_level(logging.WARNING):
        result = MediaIdentifier(InMemoryCache()).get_media_info_by_filename("Slow Horses - 05.mkv")

    assert openai.calls[0]["trigger"] == "tv_missing_season"
    assert result.outcome == IdentificationOutcome.IDENTIFIED
    assert result.media is not None
    assert result.media["tmdb_series_id"] == SERIES_ID
    assert any("OpenAI is unavailable" in record.getMessage() for record in caplog.records)


def test_openai_unavailable_and_no_tmdb_match_raises_the_outage(
    monkeypatch: pytest.MonkeyPatch, tmdb: FakeTmdb, openai: FakeOpenAI
) -> None:
    guessit_reads(monkeypatch, title="Slow Horses", media_type="tv")
    tmdb.responses["/search/tv"] = {"results": []}
    openai._answers.append(UpstreamUnavailableError("openai", "timeout"))

    with pytest.raises(UpstreamUnavailableError):
        MediaIdentifier(InMemoryCache()).get_media_info_by_filename("Slow Horses - 05.mkv")

    assert len(openai.calls) == 1


def test_season_pack_with_a_season_and_no_episode_does_not_ask_openai(
    monkeypatch: pytest.MonkeyPatch, tmdb: FakeTmdb, openai: FakeOpenAI
) -> None:
    guessit_reads(monkeypatch, title="Slow Horses", media_type="tv", season=6)

    pack = MediaIdentifier(InMemoryCache()).get_media_info_by_filename("Slow.Horses.S06.1080p.part01.rar")

    assert openai.calls == []
    assert pack.outcome == IdentificationOutcome.IDENTIFIED


def test_openai_title_that_tmdb_matches_to_another_series_ends_unidentified(
    monkeypatch: pytest.MonkeyPatch, tmdb: FakeTmdb, openai: FakeOpenAI
) -> None:
    guessit_reads(monkeypatch, title="slw hrss", media_type="tv", season=6, episode=6)
    tmdb.responses["/search/tv?query=slw hrss"] = {"results": []}
    openai._answers.append(_answered(media_type="tv", title="Slow Horsemen", season=6, episode=6))
    cache = InMemoryCache()

    result = MediaIdentifier(cache).get_media_info_by_filename("slw.hrss.s06e06.mkv")

    assert result.outcome == IdentificationOutcome.UNIDENTIFIED
    assert cache.inserted == []


def test_openai_title_confirmed_by_the_original_title_is_identified(
    monkeypatch: pytest.MonkeyPatch, tmdb: FakeTmdb, openai: FakeOpenAI
) -> None:
    guessit_reads(monkeypatch, title="cidade deus", media_type="movie", year=2002)
    tmdb.responses["/search/movie"] = {"results": []}
    tmdb.responses["/search/movie?query=Cidade de Deus"] = {
        "results": [
            {"id": 598, "title": "City of God", "original_title": "Cidade de Deus", "release_date": "2002-08-30"}
        ]
    }
    tmdb.responses["/movie/598"] = {
        "id": 598,
        "title": "City of God",
        "original_title": "Cidade de Deus",
        "release_date": "2002-08-30",
    }
    openai._answers.append(_answered(title="Cidade de Deus", year=2002))

    result = MediaIdentifier(InMemoryCache()).get_media_info_by_filename("cidade.deus.2002.mkv")

    assert result.media is not None
    assert result.media["tmdb_id"] == 598


def test_openai_recasing_the_title_is_not_a_new_title(
    monkeypatch: pytest.MonkeyPatch, tmdb: FakeTmdb, openai: FakeOpenAI
) -> None:
    guessit_reads(monkeypatch, title="possessed", media_type="movie", year=2000)
    nimble_says(monkeypatch, "tv", 0.5)
    openai._answers.append(_answered(title="Possessed", year=2000))
    cache = InMemoryCache()

    result = MediaIdentifier(cache).get_media_info_by_filename(POSSESSED_FILE)

    assert result.media is not None
    assert result.media["tmdb_id"] == MOVIE_ID
    assert cache.inserted[0]["searchable_reference"] == create_searchable_reference("possessed")


def test_nimble_turning_a_tv_reading_into_a_movie_drops_the_episode_numbers(
    monkeypatch: pytest.MonkeyPatch, tmdb: FakeTmdb
) -> None:
    guessit_reads(monkeypatch, title="Possessed", media_type="tv", year=2000, season=1, episode=2)
    nimble_says(monkeypatch, "movie", 0.95)
    cache = InMemoryCache()

    MediaIdentifier(cache).get_media_info_by_filename(POSSESSED_FILE)

    assert (cache.inserted[0]["season"], cache.inserted[0]["episode"]) == (None, None)


def test_openai_off_when_needed_ends_unidentified(monkeypatch: pytest.MonkeyPatch, tmdb: FakeTmdb) -> None:
    guessit_reads(monkeypatch, title="Possessed", media_type=None)

    result = MediaIdentifier(InMemoryCache()).get_media_info_by_filename("Possessed.mkv")

    assert result.outcome == IdentificationOutcome.UNIDENTIFIED
    assert tmdb.calls == []

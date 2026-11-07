import psycopg
import pytest
from psycopg import sql

from src.models.media_info import MediaData
from src.repositories.media_info_cache import MediaInfoCache
from tests.fakes import FakePool

ROW_ID = "8f6c5c86-7c7f-4c7b-9f32-6e8f0b7f3f11"


def _movie() -> MediaData:
    return {
        "id": None,
        "searchable_reference": "Possessed",
        "tmdb_id": 26620,
        "title": "Possessed",
        "original_title": "Possessed",
        "media_type": "movie",
        "year": 2000,
        "used_guessit": None,
        "used_tmdb": True,
        "created_at": None,
    }


def _sql_text(query: object) -> str:
    return query.as_string(None) if isinstance(query, sql.Composable) else str(query)


def test_cache_data_inserts_only_cache_columns_and_returns_the_new_id() -> None:
    pool = FakePool(rows=[{"id": ROW_ID}])
    cache = MediaInfoCache(pool_getter=pool.getter())
    record = {**_movie(), "not_a_column": "dropped"}

    stored = cache.cache_data(record)

    query, values = pool.cursor.executed[0]
    statement = _sql_text(query)
    assert '"not_a_column"' not in statement
    assert '"id"' not in statement
    assert '"created_at"' not in statement
    assert "ON CONFLICT (tmdb_id, media_type) DO NOTHING" in statement
    assert values == ["Possessed", 26620, "Possessed", "Possessed", "movie", 2000, False, True]
    assert stored["id"] == ROW_ID


def test_cache_data_conflict_returns_the_row_cached_first() -> None:
    cached_first = {**_movie(), "id": ROW_ID}
    pool = FakePool(rows=[None, cached_first])
    cache = MediaInfoCache(pool_getter=pool.getter())

    stored = cache.cache_data(_movie())

    assert stored == cached_first
    assert pool.cursor.executed[1][1] == (26620, "movie")


def test_cache_data_conflict_without_a_cached_row_raises() -> None:
    pool = FakePool(rows=[None, None])
    cache = MediaInfoCache(pool_getter=pool.getter())

    with pytest.raises(RuntimeError, match="conflicted but no cached row was found"):
        cache.cache_data(_movie())


@pytest.mark.parametrize("missing", ["tmdb_id", "title", "original_title", "media_type", "year"])
def test_cache_data_record_missing_a_required_value_raises_before_querying(missing: str) -> None:
    pool = FakePool()
    cache = MediaInfoCache(pool_getter=pool.getter())

    with pytest.raises(ValueError):
        cache.cache_data({**_movie(), missing: None})

    assert pool.cursor.executed == []


def test_is_cacheable_requires_every_not_null_column() -> None:
    assert MediaInfoCache.is_cacheable(_movie())
    assert not MediaInfoCache.is_cacheable({**_movie(), "year": None})


@pytest.mark.parametrize(("media_type", "expected"), [("movie", "movie"), ("Episode", "tv")])
def test_get_cached_by_tmdb_id_filters_by_media_type(media_type: str, expected: str) -> None:
    pool = FakePool(rows=[_movie()])
    cache = MediaInfoCache(pool_getter=pool.getter())

    result = cache.get_cached_by_tmdb_id(95480, media_type)

    statement, params = pool.cursor.executed[0]
    assert result == _movie()
    assert "tmdb_id = %s AND media_type = %s" in _sql_text(statement)
    assert params == (95480, expected)


def test_get_cached_by_tmdb_id_unknown_media_type_does_not_query() -> None:
    pool = FakePool()
    cache = MediaInfoCache(pool_getter=pool.getter())

    assert cache.get_cached_by_tmdb_id(95480, "podcast") is None
    assert pool.cursor.executed == []


def test_get_cached_tv_episode_only_matches_tv_rows() -> None:
    pool = FakePool(rows=[])
    cache = MediaInfoCache(pool_getter=pool.getter())

    cache.get_cached_tv_episode(95480, 6, 6)

    statement, params = pool.cursor.executed[0]
    assert "media_type = %s" in _sql_text(statement)
    assert "ORDER BY modified_at DESC LIMIT 1" in _sql_text(statement)
    assert params == ("tv", 95480, 6, 6)


def test_get_cached_by_id_returns_none_when_no_row_matches() -> None:
    pool = FakePool(rows=[])
    cache = MediaInfoCache(pool_getter=pool.getter())

    assert cache.get_cached_by_id(ROW_ID) is None


def test_database_error_is_raised_as_runtime_error() -> None:
    pool = FakePool(error=psycopg.OperationalError("server closed the connection"))
    cache = MediaInfoCache(pool_getter=pool.getter())

    with pytest.raises(RuntimeError, match="Error getting cached data by TMDb ID"):
        cache.get_cached_by_tmdb_id(26620, "movie")


def test_get_cached_by_obj_without_title_does_not_query() -> None:
    pool = FakePool()
    cache = MediaInfoCache(pool_getter=pool.getter())

    assert cache.get_cached_by_obj({"media_type": "movie", "title": None}) is None
    assert pool.cursor.executed == []


def test_get_cached_by_obj_matches_titles_exactly_ignoring_case() -> None:
    pool = FakePool(rows=[])
    cache = MediaInfoCache(pool_getter=pool.getter())

    cache.get_cached_by_obj({"media_type": "movie", "title": "100%", "searchable_reference": "100", "year": 2000})

    statement, params = pool.cursor.executed[0]
    text = _sql_text(statement)
    assert "ILIKE" not in text
    assert "LOWER(title) = LOWER(%s)" in text
    assert "media_type = %s" in text
    assert params == ["100%", "100", "100", "movie", 2000]


def test_get_cached_by_obj_tv_filters_by_season_and_episode() -> None:
    pool = FakePool(rows=[])
    cache = MediaInfoCache(pool_getter=pool.getter())

    cache.get_cached_by_obj({"media_type": "tv", "title": "Slow Horses", "season": 6, "episode": 6, "year": None})

    statement, params = pool.cursor.executed[0]
    assert "season = %s AND episode = %s" in _sql_text(statement)
    assert params[-2:] == [6, 6]

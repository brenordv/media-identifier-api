import psycopg
import pytest
from psycopg import sql

from src.models.media_info import MediaData
from src.repositories.media_info_cache import MediaInfoCache
from tests.fakes import FakePool


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
    pool = FakePool(rows=[{"id": "8f6c5c86-7c7f-4c7b-9f32-6e8f0b7f3f11"}])
    cache = MediaInfoCache(pool_getter=pool.getter())
    record = {**_movie(), "not_a_column": "dropped"}

    stored = cache.cache_data(record)

    query, values = pool.cursor.executed[0]
    statement = _sql_text(query)
    assert '"not_a_column"' not in statement
    assert '"id"' not in statement
    assert '"created_at"' not in statement
    assert values == ["Possessed", 26620, "Possessed", "Possessed", "movie", 2000, False, True]
    assert stored["id"] == "8f6c5c86-7c7f-4c7b-9f32-6e8f0b7f3f11"


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


def test_get_cached_by_tmdb_id_returns_the_matching_row() -> None:
    pool = FakePool(rows=[_movie()])
    cache = MediaInfoCache(pool_getter=pool.getter())

    result = cache.get_cached_by_tmdb_id(26620)

    assert result == _movie()
    assert pool.cursor.executed[0][1] == (26620,)


def test_get_cached_by_id_returns_none_when_no_row_matches() -> None:
    pool = FakePool(rows=[])
    cache = MediaInfoCache(pool_getter=pool.getter())

    assert cache.get_cached_by_id("8f6c5c86-7c7f-4c7b-9f32-6e8f0b7f3f11") is None


def test_database_error_is_raised_as_runtime_error() -> None:
    pool = FakePool(error=psycopg.OperationalError("server closed the connection"))
    cache = MediaInfoCache(pool_getter=pool.getter())

    with pytest.raises(RuntimeError, match="Error getting cached data by TMDb ID"):
        cache.get_cached_by_tmdb_id(26620)


def test_get_cached_by_obj_without_title_does_not_query() -> None:
    pool = FakePool()
    cache = MediaInfoCache(pool_getter=pool.getter())

    assert cache.get_cached_by_obj({"media_type": "movie", "title": None}) is None
    assert pool.cursor.executed == []


def test_get_cached_by_obj_tv_filters_by_season_and_episode() -> None:
    pool = FakePool(rows=[])
    cache = MediaInfoCache(pool_getter=pool.getter())

    cache.get_cached_by_obj({"media_type": "tv", "title": "Slow Horses", "season": 6, "episode": 6, "year": None})

    statement, params = pool.cursor.executed[0]
    assert "season = %s AND episode = %s" in _sql_text(statement)
    assert params[-2:] == [6, 6]

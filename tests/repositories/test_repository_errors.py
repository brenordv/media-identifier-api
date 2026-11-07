from collections.abc import Callable
from typing import Any

import psycopg
import pytest

from src.repositories.base_repository import PoolGetter
from src.repositories.media_info_cache import MediaInfoCache
from src.repositories.openai_logger import OpenAILogger
from src.repositories.request_logger import RequestLogger
from tests.fakes import FakePool

MOVIE = {
    "tmdb_id": 26620,
    "title": "Possessed",
    "original_title": "Possessed",
    "media_type": "movie",
    "year": 2000,
}

RepositoryCall = Callable[[PoolGetter], Any]

CALLS: dict[str, RepositoryCall] = {
    "cache.ensure_schema": lambda pool: MediaInfoCache(pool).ensure_schema(),
    "cache.get_cached_by_obj": lambda pool: MediaInfoCache(pool).get_cached_by_obj(MOVIE),
    "cache.get_cached_by_id": lambda pool: MediaInfoCache(pool).get_cached_by_id("a-media-id"),
    "cache.get_cached_by_tmdb_id": lambda pool: MediaInfoCache(pool).get_cached_by_tmdb_id(26620),
    "cache.get_cached_tv_episode": lambda pool: MediaInfoCache(pool).get_cached_tv_episode(95480, 6, 6),
    "cache.cache_data": lambda pool: MediaInfoCache(pool).cache_data(MOVIE),
    "requests.ensure_schema": lambda pool: RequestLogger(pool).ensure_schema(),
    "requests.log_start": lambda pool: RequestLogger(pool).log_start("/api/guess", "Fargo.mkv", "127.0.0.1"),
    "requests.log_completed": lambda pool: RequestLogger(pool).log_completed("a-request-id", 200),
    "requests.get_recent_requests": lambda pool: RequestLogger(pool).get_recent_requests(10),
    "openai.ensure_schema": lambda pool: OpenAILogger(pool).ensure_schema(),
    "openai.log": lambda pool: OpenAILogger(pool).log(1, 0, 1, 0, 2),
}


@pytest.mark.parametrize("call", CALLS.values(), ids=CALLS.keys())
def test_database_error_is_raised_as_runtime_error(call: RepositoryCall) -> None:
    pool = FakePool(error=psycopg.OperationalError("server closed the connection unexpectedly"))

    with pytest.raises(RuntimeError) as raised:
        call(pool.getter())

    assert isinstance(raised.value.__cause__, psycopg.OperationalError)


@pytest.mark.parametrize(
    "call",
    [CALLS["cache.ensure_schema"], CALLS["requests.ensure_schema"], CALLS["openai.ensure_schema"]],
    ids=["cache", "requests", "openai"],
)
def test_ensure_schema_creates_the_extension_table_and_indexes(call: RepositoryCall) -> None:
    pool = FakePool()

    call(pool.getter())

    statements = [str(statement) for statement, _ in pool.cursor.executed]
    assert 'CREATE EXTENSION IF NOT EXISTS "uuid-ossp"' in statements[0]
    assert any("CREATE TABLE IF NOT EXISTS" in statement for statement in statements)
    assert any("CREATE INDEX IF NOT EXISTS" in statement for statement in statements)


@pytest.mark.parametrize(
    "call",
    [CALLS["cache.cache_data"], CALLS["requests.log_start"], CALLS["openai.log"]],
    ids=["cache_data", "log_start", "openai_log"],
)
def test_insert_returning_no_row_raises_runtime_error(call: RepositoryCall) -> None:
    pool = FakePool(rows=[])

    with pytest.raises(RuntimeError, match="returned no id"):
        call(pool.getter())

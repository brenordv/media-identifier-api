import os
from typing import Optional

from psycopg2.pool import SimpleConnectionPool

from src.repositories.media_info_cache import MediaInfoCache
from src.repositories.openai_logger import OpenAILogger
from src.repositories.request_logger import RequestLogger

_db_pool: Optional[SimpleConnectionPool] = None
_repos_initialized = set()

def _require_env(name: str) -> str:
    value = os.environ.get(name)
    if value is None or value.strip() == "":
        raise ValueError(f"Environment variable '{name}' must be set to connect to the database.")
    return value


def _get_pool() -> SimpleConnectionPool:
    global _db_pool

    if _db_pool is not None:
        return _db_pool

    host = _require_env("POSTGRES_HOST")
    port = int(_require_env("POSTGRES_PORT"))
    user = _require_env("POSTGRES_USER")
    password = _require_env("POSTGRES_PASSWORD")
    dbname = os.environ.get("POSTGRES_DB", "extended_media_info")

    _db_pool = SimpleConnectionPool(
        minconn=1,
        maxconn=10,
        host=host,
        port=port,
        user=user,
        password=password,
        dbname=dbname,
    )

    return _db_pool


def get_repository(repo_name: str):
    pool = _get_pool()
    repo_name = repo_name.lower()
    skip_database_initialization = repo_name in _repos_initialized
    _repos_initialized.add(repo_name)

    if repo_name == "cache":
        return MediaInfoCache(pool, skip_database_initialization=skip_database_initialization)

    if repo_name == "request_logger":
        return RequestLogger(pool, skip_database_initialization=skip_database_initialization)

    if repo_name == "openai_logger":
        return OpenAILogger(pool, skip_database_initialization=skip_database_initialization)

    raise ValueError(f"Repository '{repo_name}' is not recognized or not implemented.")
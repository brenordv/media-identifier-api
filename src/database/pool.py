"""PostgreSQL connection settings read from the environment."""

import os

from psycopg.conninfo import make_conninfo
from raccoontools_db import PoolConfig

DEFAULT_DATABASE_NAME = "extended_media_info"
POOL_MIN_SIZE = 1
POOL_MAX_SIZE = 10


def _require_env(name: str) -> str:
    value = os.environ.get(name)
    if value is None or value.strip() == "":
        raise ValueError(f"Environment variable '{name}' must be set to connect to the database.")
    return value


def build_conninfo() -> str:
    """Build a libpq connection string from the ``POSTGRES_*`` environment variables.

    ``POSTGRES_HOST``, ``POSTGRES_PORT``, ``POSTGRES_USER`` and ``POSTGRES_PASSWORD`` are required;
    ``POSTGRES_DB`` defaults to ``extended_media_info``.

    Returns:
        The connection string.

    Raises:
        ValueError: If a required variable is missing or ``POSTGRES_PORT`` is not a number.
    """
    port = _require_env("POSTGRES_PORT")
    if not port.strip().isdigit():
        raise ValueError("Environment variable 'POSTGRES_PORT' must be a number.")

    return make_conninfo(
        host=_require_env("POSTGRES_HOST"),
        port=port.strip(),
        user=_require_env("POSTGRES_USER"),
        password=_require_env("POSTGRES_PASSWORD"),
        dbname=os.environ.get("POSTGRES_DB") or DEFAULT_DATABASE_NAME,
    )


def build_pool_config() -> PoolConfig:
    """Build the connection pool configuration from the environment.

    Returns:
        The pool configuration.

    Raises:
        ValueError: If the database settings are incomplete (see :func:`build_conninfo`).
    """
    return PoolConfig(conn_info=build_conninfo(), min_size=POOL_MIN_SIZE, max_size=POOL_MAX_SIZE)

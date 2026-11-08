"""Base class for repositories that borrow connections from the shared PostgreSQL pool."""

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import Any

from psycopg import Connection
from psycopg_pool import ConnectionPool
from raccoontools_db import get_pool
from simple_log_factory_ext_otel import TracedLogger

PoolGetter = Callable[[], ConnectionPool[Any]]


class BaseRepository:
    """Gives subclasses pooled connections and a logger.

    Args:
        logger: Logger used by the repository.
        pool_getter: Returns the pool to borrow connections from. Defaults to the process-wide pool, which must be
            created (``raccoontools_db.create_pool``) before the first query.
    """

    def __init__(self, logger: TracedLogger, pool_getter: PoolGetter = get_pool) -> None:
        self._logger = logger
        self._pool_getter = pool_getter

    @contextmanager
    def _get_connection(self) -> Iterator[Connection[Any]]:
        """Borrow a connection; its transaction commits on normal exit and rolls back on an exception."""
        with self._pool_getter().connection() as conn:
            yield conn

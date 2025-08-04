from logging import Logger
from contextlib import contextmanager

from psycopg2.pool import SimpleConnectionPool


class BaseRepository:
    def __init__(self, conn_pool: SimpleConnectionPool, logger: Logger):
        self._conn_pool = conn_pool
        self._logger = logger

    @contextmanager
    def _get_connection(self):
        conn = self._conn_pool.getconn()
        try:
            yield conn
        finally:
            self._conn_pool.putconn(conn)

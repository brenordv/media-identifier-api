import psycopg2
from psycopg2.pool import SimpleConnectionPool

from src.repositories.base_repository import BaseRepository
from src.utils import get_otel_log_handler


_logger = get_otel_log_handler("RequestLogger")


class RequestLogger(BaseRepository):
    def __init__(self, conn_pool: SimpleConnectionPool, skip_database_initialization: bool = False):
        super().__init__(conn_pool, _logger)
        if not skip_database_initialization:
            self._ensure_table_exists()

    def _ensure_table_exists(self):
        try:
            with self._get_connection() as conn:
                with conn.cursor() as cursor:
                    self._logger.debug("Enabling uuid-ossp extension")
                    cursor.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp";')

                    self._logger.debug("Creating request_history table if it does not exist")
                    create_table_query = """
                                         CREATE TABLE IF NOT EXISTS request_history (
                                             id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                                             endpoint TEXT NOT NULL,
                                             filename TEXT NOT NULL,
                                             requester_ip TEXT NOT NULL,
                                             result_status INTEGER NULL,
                                             result_media_id UUID NULL,
                                             received_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                                             responded_at TIMESTAMP NULL,
                                             error_message TEXT NULL,
                                             elapsed_time INTERVAL GENERATED ALWAYS AS (responded_at - received_at) STORED
                                             );"""
                    cursor.execute(create_table_query)

                    self._logger.debug("Creating indexes for request_history table")
                    cursor.execute(
                        """
                        CREATE INDEX IF NOT EXISTS idx_request_history_received_at_desc
                        ON request_history (received_at DESC);
                        """
                    )
                    conn.commit()
        except psycopg2.Error as e:
            error_message = f"Error creating the request logger table: {str(e)}"
            self._logger.error(error_message)
            raise RuntimeError(error_message) from e

    @_logger.trace("log_start")
    def log_start(self, endpoint: str, filename: str, requester_ip: str):
        try:
            self._logger.debug(f"Logging request start for {filename} from {requester_ip}")
            with self._get_connection() as conn:
                with conn.cursor() as cursor:
                    insert_query = """
                    INSERT INTO request_history (endpoint, filename, requester_ip, received_at)
                    VALUES (%s, %s, %s, CURRENT_TIMESTAMP)
                    RETURNING id;
                    """
                    cursor.execute(insert_query, (endpoint, filename, requester_ip))
                    request_id = cursor.fetchone()[0]
                    conn.commit()

                    self._logger.debug(f"Request logged with ID: {request_id}")
                    return str(request_id)
        except psycopg2.Error as e:
            error_message = f"Error logging request start: {str(e)}"
            self._logger.error(error_message)
            raise RuntimeError(error_message) from e

    @_logger.trace("log_completed")
    def log_completed(self, request_id: str, status_code: int, result_media_id: str = None, error_message: str = None):
        try:
            self._logger.debug(f"Logging request completion for ID {request_id} with status {status_code}, and result media ID {result_media_id}")
            with self._get_connection() as conn:
                with conn.cursor() as cursor:
                    update_query = """
                    UPDATE request_history
                    SET responded_at = CURRENT_TIMESTAMP,
                        result_status = %s,
                        result_media_id = %s,
                        error_message = %s
                    WHERE id = %s;
                    """
                    cursor.execute(update_query, (status_code, result_media_id, error_message, request_id))
                    conn.commit()

                    self._logger.debug(f"Request ID {request_id} updated successfully")
        except psycopg2.Error as e:
            error_message = f"Error logging request completion: {str(e)}"
            self._logger.error(error_message)
            raise RuntimeError(error_message) from e

    @_logger.trace("get_recent_requests")
    def get_recent_requests(self, limit: int = 100):
        try:
            self._logger.debug(f"Fetching recent requests with limit {limit}")
            with self._get_connection() as conn:
                with conn.cursor() as cursor:
                    select_query = """
                    SELECT id, filename, requester_ip, result_status, result_media_id, received_at, responded_at, elapsed_time, error_message
                    FROM request_history
                    ORDER BY received_at DESC
                    LIMIT %s;
                    """
                    cursor.execute(select_query, (limit,))
                    results = cursor.fetchall()

                    self._logger.debug(f"Fetched {len(results)} recent requests")
                    return [{
                        "id": str(row[0]),
                        "filename": row[1],
                        "requester_ip": row[2],
                        "result_status": row[3],
                        "result_media_id": row[4],
                        "received_at": row[5],
                        "responded_at": row[6],
                        "elapsed_time": row[7],
                        "error_message": row[8]
                    } for row in results]
        except psycopg2.Error as e:
            error_message = f"Error fetching recent requests: {str(e)}"
            self._logger.error(error_message)
            raise RuntimeError(error_message) from e
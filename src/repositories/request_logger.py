"""Repository for the ``request_history`` table, which records every API request and its outcome."""

from typing import Any

import psycopg
from opentelemetry import trace
from psycopg.rows import dict_row
from raccoontools_db import get_pool

from src.repositories.base_repository import BaseRepository, PoolGetter
from src.utils import get_otel_log_handler

_logger = get_otel_log_handler("RequestLogger")


class RequestLogger(BaseRepository):
    """Records requests when they start and when they complete.

    Args:
        pool_getter: Returns the connection pool to use.
    """

    def __init__(self, pool_getter: PoolGetter = get_pool) -> None:
        super().__init__(_logger, pool_getter)

    @_logger.trace("log_start")
    def log_start(self, endpoint: str, filename: str, requester_ip: str) -> str:
        """Record that a request arrived.

        Args:
            endpoint: Route that received the request.
            filename: The file name or query the request carried.
            requester_ip: Client address.

        Returns:
            The id of the new ``request_history`` row.

        Raises:
            RuntimeError: If the insert fails.
        """
        span = trace.get_current_span()
        if span.is_recording():
            span.set_attributes(
                {
                    "db.table": "request_history",
                    "db.operation": "insert",
                    "http.endpoint": endpoint,
                    "media.input_filename": filename,
                    "http.client_ip": requester_ip,
                }
            )
        try:
            self._logger.debug(f"Logging request start for {filename!r} from {requester_ip}")
            with self._get_connection() as conn, conn.cursor() as cursor:
                cursor.execute(
                    "INSERT INTO request_history (endpoint, filename, requester_ip, received_at) "
                    "VALUES (%s, %s, %s, CURRENT_TIMESTAMP) RETURNING id;",
                    (endpoint, filename, requester_ip),
                )
                row = cursor.fetchone()
        except psycopg.Error as e:
            raise RuntimeError(f"Error logging request start: {e}") from e

        if row is None:
            raise RuntimeError("Error logging request start: the insert returned no id")

        request_id = str(row[0])
        self._logger.debug(f"Request logged with ID: {request_id}")
        return request_id

    @_logger.trace("log_completed")
    def log_completed(
        self,
        request_id: str,
        status_code: int,
        result_media_id: str | None = None,
        error_message: str | None = None,
        outcome: str | None = None,
        decided_by: str | None = None,
    ) -> None:
        """Record how a request ended.

        Args:
            request_id: Id returned by :meth:`log_start`.
            status_code: HTTP status sent to the client.
            result_media_id: Id of the cached media returned, if any.
            error_message: Operator-facing description of a failure, if any.
            outcome: ``identified``, ``not_media`` or ``unidentified`` when identification reached a verdict.
            decided_by: The step that settled the media type or the ``not_media`` verdict (``guessit``, ``nimble``,
                ``openai`` or ``request``), if any.

        Raises:
            RuntimeError: If the update fails.
        """
        span = trace.get_current_span()
        if span.is_recording():
            span.set_attributes(
                {
                    "db.table": "request_history",
                    "db.operation": "update",
                    "http.request_id": request_id,
                    "http.status_code": status_code,
                }
            )
            if result_media_id:
                span.set_attribute("media.id", result_media_id)
        try:
            self._logger.debug(
                f"Logging request completion for ID {request_id} with status {status_code}, "
                f"and result media ID {result_media_id}"
            )
            with self._get_connection() as conn, conn.cursor() as cursor:
                cursor.execute(
                    "UPDATE request_history SET responded_at = CURRENT_TIMESTAMP, result_status = %s, "
                    "result_media_id = %s, error_message = %s, outcome = %s, decided_by = %s WHERE id = %s;",
                    (status_code, result_media_id, error_message, outcome, decided_by, request_id),
                )
            self._logger.debug(f"Request ID {request_id} updated successfully")
        except psycopg.Error as e:
            raise RuntimeError(f"Error logging request completion: {e}") from e

    @_logger.trace("get_recent_requests")
    def get_recent_requests(self, limit: int = 100) -> list[dict[str, Any]]:
        """Return the most recent requests, newest first.

        Args:
            limit: Maximum number of requests to return.

        Returns:
            One dict per request with its id, file name, client address, status, result id, timestamps, elapsed
            time, error message, outcome and deciding step.

        Raises:
            RuntimeError: If the query fails.
        """
        try:
            self._logger.debug(f"Fetching recent requests with limit {limit}")
            with self._get_connection() as conn, conn.cursor(row_factory=dict_row) as cursor:
                cursor.execute(
                    "SELECT id, filename, requester_ip, result_status, result_media_id, received_at, responded_at, "
                    "elapsed_time, error_message, outcome, decided_by FROM request_history "
                    "ORDER BY received_at DESC LIMIT %s;",
                    (limit,),
                )
                rows = cursor.fetchall()
        except psycopg.Error as e:
            raise RuntimeError(f"Error fetching recent requests: {e}") from e

        self._logger.debug(f"Fetched {len(rows)} recent requests")
        return [
            {
                **row,
                "id": str(row["id"]),
                "result_media_id": str(row["result_media_id"]) if row["result_media_id"] is not None else None,
            }
            for row in rows
        ]

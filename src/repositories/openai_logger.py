"""Repository for the ``openai_history`` table, which records the tokens each OpenAI call used."""

import psycopg
from opentelemetry import trace
from raccoontools_db import get_pool

from src.repositories.base_repository import BaseRepository, PoolGetter
from src.utils import get_otel_log_handler, get_request_id

_logger = get_otel_log_handler("OpenAILogger")


class OpenAILogger(BaseRepository):
    """Records OpenAI token usage per request.

    Args:
        pool_getter: Returns the connection pool to use.
    """

    def __init__(self, pool_getter: PoolGetter = get_pool) -> None:
        super().__init__(_logger, pool_getter)

    def ensure_schema(self) -> None:
        """Create the ``openai_history`` table and its index when they do not exist.

        Raises:
            RuntimeError: If the database rejects the DDL.
        """
        try:
            with self._get_connection() as conn, conn.cursor() as cursor:
                self._logger.debug("Enabling uuid-ossp extension")
                cursor.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp";')

                self._logger.debug("Creating openai_history table if it does not exist")
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS openai_history (
                        id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                        request_id UUID NOT NULL,
                        input_tokens INTEGER NOT NULL,
                        cached_tokens INTEGER NOT NULL,
                        output_tokens INTEGER NOT NULL,
                        reasoning_tokens INTEGER NOT NULL,
                        total_tokens INTEGER NOT NULL,
                        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                    );
                    """
                )

                self._logger.debug("Creating indexes for openai_history table")
                cursor.execute(
                    "CREATE INDEX IF NOT EXISTS idx_openai_history_request_id ON openai_history (request_id);"
                )
        except psycopg.Error as e:
            raise RuntimeError(f"Error creating the OpenAI request logger table: {e}") from e

    @_logger.trace("log")
    def log(
        self,
        input_tokens: int,
        cached_tokens: int,
        output_tokens: int,
        reasoning_tokens: int,
        total_tokens: int,
    ) -> str:
        """Record the token usage of one OpenAI call for the request being handled.

        Args:
            input_tokens: Prompt tokens.
            cached_tokens: Prompt tokens served from OpenAI's cache.
            output_tokens: Completion tokens.
            reasoning_tokens: Reasoning tokens included in the completion.
            total_tokens: Total tokens billed.

        Returns:
            The id of the new ``openai_history`` row.

        Raises:
            RuntimeError: If the insert fails.
        """
        span = trace.get_current_span()
        if span.is_recording():
            span.set_attributes(
                {
                    "db.table": "openai_history",
                    "db.operation": "insert",
                    "ai.usage.input_tokens": input_tokens,
                    "ai.usage.output_tokens": output_tokens,
                    "ai.usage.total_tokens": total_tokens,
                }
            )
        request_id = get_request_id()
        try:
            self._logger.debug(f"Logging OpenAI request completion for request ID {request_id}")
            with self._get_connection() as conn, conn.cursor() as cursor:
                cursor.execute(
                    "INSERT INTO openai_history (input_tokens, cached_tokens, output_tokens, reasoning_tokens, "
                    "total_tokens, request_id, created_at) "
                    "VALUES (%s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP) RETURNING id;",
                    (input_tokens, cached_tokens, output_tokens, reasoning_tokens, total_tokens, request_id),
                )
                row = cursor.fetchone()
        except psycopg.Error as e:
            raise RuntimeError(f"Error logging OpenAI token usage: {e}") from e

        if row is None:
            raise RuntimeError("Error logging OpenAI token usage: the insert returned no id")

        self._logger.debug(f"Request logged with ID: {row[0]}")
        return str(row[0])

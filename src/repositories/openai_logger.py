import psycopg2
from psycopg2.pool import SimpleConnectionPool

from src.repositories.base_repository import BaseRepository
from src.utils import get_request_id, get_otel_log_handler


_logger = get_otel_log_handler("OpenAILogger")


class OpenAILogger(BaseRepository):
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

                    self._logger.debug("Creating openai_history table if it does not exist")
                    create_table_query = """
                                         CREATE TABLE IF NOT EXISTS openai_history (
                                             id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                                             request_id UUID NOT NULL,
                                             input_tokens INTEGER NOT NULL,
                                             cached_tokens INTEGER NOT NULL,
                                             output_tokens INTEGER NOT NULL,
                                             reasoning_tokens INTEGER NOT NULL,
                                             total_tokens INTEGER NOT NULL,
                                             created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                                             );"""
                    cursor.execute(create_table_query)

                    self._logger.debug("Creating indexes for openai_history table")
                    cursor.execute(
                        """
                        CREATE INDEX IF NOT EXISTS idx_openai_history_request_id
                        ON openai_history (request_id);
                        """
                    )
                    conn.commit()
        except psycopg2.Error as e:
            error_message = f"Error creating the OpenAI request logger table: {str(e)}"
            self._logger.error(error_message)
            raise RuntimeError(error_message) from e

    @_logger.trace("log")
    def log(self,
            input_tokens: int,
            cached_tokens: int,
            output_tokens: int,
            reasoning_tokens: int,
            total_tokens: int):
        try:
            request_id = get_request_id()

            self._logger.debug(f"Logging OpenAI request completion for request ID {request_id}")

            with self._get_connection() as conn:
                with conn.cursor() as cursor:
                    insert_query = """
                    INSERT INTO openai_history (input_tokens, cached_tokens, output_tokens, reasoning_tokens, total_tokens, request_id, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
                    RETURNING id;
                    """

                    cursor.execute(insert_query, (input_tokens, cached_tokens, output_tokens, reasoning_tokens, total_tokens, request_id))
                    openai_request_log_id = cursor.fetchone()[0]
                    conn.commit()

                    self._logger.debug(f"Request logged with ID: {openai_request_log_id}")
                    return str(openai_request_log_id)
        except psycopg2.Error as e:
            error_message = f"Error logging request start: {str(e)}"
            self._logger.error(error_message)
            raise RuntimeError(error_message) from e
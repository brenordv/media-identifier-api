import psycopg2
from psycopg2.pool import SimpleConnectionPool
from simple_log_factory.log_factory import log_factory

from src.utils import get_request_id


class OpenAILogger:
    def __init__(self, conn_pool: SimpleConnectionPool):
        self._conn_pool = conn_pool
        self._logger = log_factory("OpenAILogger", unique_handler_types=True)
        self._ensure_table_exists()


    def _get_connection(self):
        return self._conn_pool.getconn()

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
                    conn.commit()
        except psycopg2.Error as e:
            error_message = f"Error creating the OpenAI request logger table: {str(e)}"
            self._logger.error(error_message)
            raise RuntimeError(error_message) from e

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
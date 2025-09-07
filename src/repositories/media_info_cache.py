import psycopg2
from psycopg2.pool import SimpleConnectionPool
from simple_log_factory.log_factory import log_factory

from src.converters.create_searchable_reference import create_searchable_reference
from src.repositories.base_repository import BaseRepository
from src.utils import is_valid_year


class MediaInfoCache(BaseRepository):
    def __init__(self, conn_pool: SimpleConnectionPool):
        super().__init__(conn_pool, log_factory("Cache", unique_handler_types=True))
        self._ensure_table_exists()
        self._required_columns = [
            'searchable_reference',
            'tmdb_id',
            'title',
            'original_title',
            'media_type',
            'year']

    def _ensure_table_exists(self):
        try:
            with self._get_connection() as conn:
                with conn.cursor() as cursor:
                    self._logger.debug("Enabling uuid-ossp extension")
                    cursor.execute("CREATE EXTENSION IF NOT EXISTS \"uuid-ossp\";")

                    self._logger.debug("Creating cached_media table if it does not exist")
                    create_table_query = """
                                         CREATE TABLE IF NOT EXISTS cached_media (
                                             id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                                             searchable_reference TEXT NULL,
                                             tmdb_id INTEGER NOT NULL UNIQUE,
                                             tmdb_series_id INTEGER NULL,
                                             imdb_id TEXT NULL,
                                             tvdb_id INTEGER NULL,
                                             tvrage_id INTEGER NULL,
                                             wikidata_id TEXT NULL,
                                             facebook_id TEXT NULL,
                                             instagram_id TEXT NULL,
                                             twitter_id TEXT NULL,
                                             genres TEXT[] NULL,
                                             title TEXT NOT NULL,
                                             original_title TEXT NOT NULL,
                                             overview TEXT NULL,
                                             episode_title TEXT NULL,
                                             season INTEGER NULL,
                                             episode INTEGER NULL,
                                             original_language TEXT NULL,
                                             media_type TEXT NOT NULL,
                                             year INTEGER NOT NULL,
                                             tagline TEXT NULL,
                                             used_guessit BOOLEAN NOT NULL DEFAULT FALSE,
                                             used_tmdb BOOLEAN NOT NULL DEFAULT FALSE,
                                             used_openai BOOLEAN NOT NULL DEFAULT FALSE,
                                             created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                                             modified_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                                             );"""
                    cursor.execute(create_table_query)
                    conn.commit()
        except psycopg2.Error as e:
            error_message = f"Error creating the cache table: {str(e)}"
            self._logger.error(error_message)
            raise RuntimeError(error_message) from e

    @staticmethod
    def _prepare_values_for_cache(new_record: dict, target_keys: list):
        values = []
        for key, value in new_record.items():
            if key not in target_keys:
                continue

            if key in ['used_guessit', 'used_tmdb', 'used_openai']:
                values.append(bool(value))
                continue

            values.append(value)

        return values

    def get_cached_by_obj(self, obj):
        try:
            self._logger.debug(f"Getting cached data by object for [{obj}]")

            if obj is None:
                self._logger.debug("No object provided, returning None")
                return None

            media_type = obj.get('media_type')
            title = obj.get('title')
            searchable_reference_from_title = create_searchable_reference(title)
            searchable_reference = obj.get('searchable_reference')
            year = obj.get('year')

            if any(x is None for x in [media_type, title]):
                self._logger.debug("Object does not contain all required fields, returning None")
                return None

            with self._get_connection() as conn:
                with conn.cursor() as cursor:
                    base_query = "SELECT * FROM cached_media WHERE (title ILIKE %s or searchable_reference ILIKE %s or searchable_reference ILIKE %s) and media_type ILIKE %s"

                    query_args = ()

                    if media_type == 'tv':
                        episode_number = obj.get('episode')
                        season_number = obj.get('season')

                        if episode_number is None and season_number is None:
                            self._logger.debug(f"Object does not contain season or episode number, returning None. Object: {obj}")
                            return None

                        query = f"{base_query} and season = %s and episode = %s"
                        if is_valid_year(year):
                            query = f"{query} and year = %s"
                            query_args = (title, searchable_reference_from_title, searchable_reference, media_type, season_number, episode_number, year)
                            cursor.execute(query, query_args)
                        else:
                            query_args = (title, searchable_reference_from_title, searchable_reference, media_type, season_number, episode_number)
                            cursor.execute(query, query_args)
                    elif media_type == 'movie':
                        if is_valid_year(year):
                            query = f"{base_query} and year = %s"
                            query_args = (title, searchable_reference_from_title, searchable_reference, media_type, year)
                            cursor.execute(query, query_args)
                        else:
                            query_args = (title, searchable_reference_from_title, searchable_reference, media_type)
                            cursor.execute(base_query, query_args)

                    else:
                        self._logger.debug("Object does not contain a valid media type, returning None")
                        return None

                    result = cursor.fetchone()
                    if result:
                        return dict(zip([desc[0] for desc in cursor.description], result))

                    self._logger.debug(f"No cached data found for object. Query Args: {query_args}")

                    return None
        except psycopg2.Error as e:
            error_message = f"Error getting cached data by object: {str(e)}"
            self._logger.error(error_message)
            raise RuntimeError(error_message) from e

    def get_cached(self, search_term: str, media_type: str, search_prop_name: str = "searchable_reference"):
        try:
            self._logger.debug(f"Getting cached data for {search_prop_name}: {search_term}")
            with self._get_connection() as conn:
                with conn.cursor() as cursor:
                    if media_type is None:
                        query = f"SELECT * FROM cached_media WHERE {search_prop_name} = %s;"
                        cursor.execute(query, (search_term,))
                    else:
                        query = f"SELECT * FROM cached_media WHERE {search_prop_name} = %s AND media_type = %s;"
                        cursor.execute(query, (search_term, media_type,))

                    result = cursor.fetchone()
                    if result:
                        return dict(zip([desc[0] for desc in cursor.description], result))
                    return None
        except psycopg2.Error as e:
            error_message = f"Error getting cached data: {str(e)}"
            self._logger.error(error_message)
            raise RuntimeError(error_message) from e

    def cache_data(self, new_record: dict):
        try:
            self._logger.debug(f"Caching record with title: {new_record.get('title', '[Unknown]')}")
            with self._get_connection() as conn:
                with conn.cursor() as cursor:
                    # Ensure all required columns are present
                    if not all(col in new_record for col in self._required_columns):
                        raise ValueError("Missing required fields in the record")

                    keys = [key for key in new_record.keys() if key not in ['id', 'created_at', 'modified_at']]
                    values = self._prepare_values_for_cache(new_record, keys)

                    # Prepare the insert query
                    columns = ', '.join(keys)
                    placeholders = ', '.join(['%s'] * len(keys))
                    query = f"INSERT INTO cached_media ({columns}) VALUES ({placeholders}) RETURNING id;"

                    cursor.execute(query, tuple(values))
                    new_id = cursor.fetchone()[0]
                    conn.commit()
                    self._logger.debug(f"Record cached with ID: {new_id}")

                    return {
                        **new_record,
                        'id': str(new_id)
                    }
        except psycopg2.Error as e:
            error_message = f"Error caching record: {str(e)}"
            self._logger.error(error_message)
            raise RuntimeError(error_message) from e

    def update_cache(self, new_record: dict):
        try:
            self._logger.debug(f"Updating cache for record with title: {new_record.get('title', '[Unknown]')}")
            with self._get_connection() as conn:
                with conn.cursor() as cursor:
                    # Ensure the record has an ID to update
                    if 'id' not in new_record:
                        raise ValueError("Record must have an 'id' field to update")

                    prepared_new_record = {
                        **new_record,
                    }

                    for forbidden_key in ['id', 'created_at', 'modified_at']:
                        prepared_new_record.pop(forbidden_key, None)

                    set_clause = ', '.join([f"{key} = %s" for key in prepared_new_record])
                    query = f"UPDATE cached_media SET {set_clause}, modified_at = CURRENT_TIMESTAMP WHERE id = %s;"

                    cursor.execute(query, tuple(prepared_new_record.values()) + (new_record['id'],))
                    conn.commit()
                    self._logger.debug("Cache updated successfully")

        except psycopg2.Error as e:
            error_message = f"Error updating cache: {str(e)}"
            self._logger.error(error_message)
            raise RuntimeError(error_message) from e

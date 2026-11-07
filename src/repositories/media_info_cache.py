"""Repository for the ``cached_media`` table, which stores identified movies and TV episodes.

A row is identified by ``(tmdb_id, media_type)``: ``tmdb_id`` is the TMDB id of the row's own entity (a movie, or
a TV episode), and TMDB numbers movies, series and episodes independently. A TV row keeps its series id in
``tmdb_series_id``.
"""

from typing import Any

import psycopg
from opentelemetry import trace
from psycopg import sql
from psycopg.rows import dict_row
from raccoontools_db import get_pool

from src.converters.create_searchable_reference import create_searchable_reference
from src.media_identifiers.constants import TV
from src.media_identifiers.media_type_helpers import normalize_media_type
from src.models.media_info import MediaData
from src.repositories.base_repository import BaseRepository, PoolGetter
from src.utils import get_otel_log_handler, is_valid_year

_logger = get_otel_log_handler("Cache")

CACHE_COLUMNS: tuple[str, ...] = (
    "searchable_reference",
    "tmdb_id",
    "tmdb_series_id",
    "imdb_id",
    "tvdb_id",
    "tvrage_id",
    "wikidata_id",
    "facebook_id",
    "instagram_id",
    "twitter_id",
    "genres",
    "title",
    "original_title",
    "overview",
    "episode_title",
    "season",
    "episode",
    "original_language",
    "media_type",
    "year",
    "tagline",
    "used_guessit",
    "used_tmdb",
    "used_openai",
)
"""Columns a cached record may write; ``id``, ``created_at`` and ``modified_at`` are filled by the database."""

REQUIRED_COLUMNS: tuple[str, ...] = ("tmdb_id", "title", "original_title", "media_type", "year")
"""Columns declared NOT NULL without a default."""

_SERVICE_FLAG_COLUMNS = ("used_guessit", "used_tmdb", "used_openai")


class MediaInfoCache(BaseRepository):
    """Reads and writes cached media records.

    Args:
        pool_getter: Returns the connection pool to use.
    """

    def __init__(self, pool_getter: PoolGetter = get_pool) -> None:
        super().__init__(_logger, pool_getter)

    @staticmethod
    def is_cacheable(record: MediaData) -> bool:
        """Tell whether a record has every value the table requires.

        Args:
            record: The media record.

        Returns:
            True when no NOT NULL column would be empty.
        """
        return all(record.get(column) is not None for column in REQUIRED_COLUMNS)

    @_logger.trace("get_cached_by_obj")
    def get_cached_by_obj(self, obj: MediaData | None) -> MediaData | None:
        """Find a cached record matching an identified title, media type and year (and season/episode for TV).

        Titles match case-insensitively and exactly, against the title or the search key.

        Args:
            obj: The identified media; needs at least ``title`` and ``media_type``.

        Returns:
            The cached record, or None when nothing matches or ``obj`` lacks the fields to search with.

        Raises:
            RuntimeError: If the query fails.
        """
        span = trace.get_current_span()
        if span.is_recording():
            span.set_attributes({"db.table": "cached_media", "db.operation": "select"})

        if obj is None:
            self._logger.debug("No object provided, returning None")
            return None

        media_type = normalize_media_type(obj.get("media_type"))
        title = obj.get("title")
        year = obj.get("year")

        if media_type is None or title is None:
            self._logger.debug("Object does not contain all required fields, returning None")
            return None

        query = (
            "SELECT * FROM cached_media "
            "WHERE (LOWER(title) = LOWER(%s) OR LOWER(searchable_reference) = LOWER(%s) "
            "OR LOWER(searchable_reference) = LOWER(%s)) "
            "AND media_type = %s"
        )
        query_args: list[Any] = [title, create_searchable_reference(title), obj.get("searchable_reference"), media_type]

        if media_type == TV:
            season_number = obj.get("season")
            episode_number = obj.get("episode")
            if season_number is None and episode_number is None:
                self._logger.debug("Object does not contain season or episode number, returning None.")
                return None
            query += " AND season = %s AND episode = %s"
            query_args += [season_number, episode_number]

        if is_valid_year(year):
            query += " AND year = %s"
            query_args.append(year)

        try:
            with self._get_connection() as conn, conn.cursor(row_factory=dict_row) as cursor:
                cursor.execute(query, query_args)
                result = cursor.fetchone()
        except psycopg.Error as e:
            raise RuntimeError(f"Error getting cached data by object: {e}") from e

        if result is None:
            self._logger.debug(f"No cached data found for object. Query Args: {query_args!r}")
        return result

    @_logger.trace("get_cached_by_id")
    def get_cached_by_id(self, media_id: str) -> MediaData | None:
        """Fetch a cached record by its id.

        Args:
            media_id: The record's UUID, as a string.

        Returns:
            The cached record, or None when no record has that id.

        Raises:
            RuntimeError: If the query fails.
        """
        span = trace.get_current_span()
        if span.is_recording():
            span.set_attributes({"db.table": "cached_media", "db.operation": "select", "media.id": media_id})

        try:
            with self._get_connection() as conn, conn.cursor(row_factory=dict_row) as cursor:
                cursor.execute("SELECT * FROM cached_media WHERE id = %s;", (media_id,))
                return cursor.fetchone()
        except psycopg.Error as e:
            raise RuntimeError(f"Error getting cached data by id: {e}") from e

    @_logger.trace("get_cached_by_tmdb_id")
    def get_cached_by_tmdb_id(self, tmdb_id: int, media_type: str) -> MediaData | None:
        """Fetch the cached movie or episode with this TMDB id.

        Args:
            tmdb_id: TMDB id of the movie or episode.
            media_type: ``movie`` or ``tv``; required because TMDB ids repeat across media types.

        Returns:
            The cached record, or None when none matches (or ``media_type`` is not recognized).

        Raises:
            RuntimeError: If the query fails.
        """
        span = trace.get_current_span()
        if span.is_recording():
            span.set_attributes(
                {"db.table": "cached_media", "db.operation": "select", "tmdb.id": tmdb_id, "media.type": media_type}
            )

        normalized_media_type = normalize_media_type(media_type)
        if normalized_media_type is None:
            self._logger.debug(f"Media type {media_type!r} is not valid for a TMDb ID lookup.")
            return None

        try:
            self._logger.debug(f"Getting cached {normalized_media_type} by TMDb ID: {tmdb_id}")
            with self._get_connection() as conn, conn.cursor(row_factory=dict_row) as cursor:
                cursor.execute(
                    "SELECT * FROM cached_media WHERE tmdb_id = %s AND media_type = %s;",
                    (tmdb_id, normalized_media_type),
                )
                return cursor.fetchone()
        except psycopg.Error as e:
            raise RuntimeError(f"Error getting cached data by TMDb ID: {e}") from e

    @_logger.trace("get_cached_tv_episode")
    def get_cached_tv_episode(self, tmdb_series_id: int, season: int, episode: int) -> MediaData | None:
        """Fetch a cached TV episode by series id, season and episode number.

        Args:
            tmdb_series_id: TMDB id of the series.
            season: Season number.
            episode: Episode number.

        Returns:
            The most recently modified matching episode, or None when it is not cached.

        Raises:
            RuntimeError: If the query fails.
        """
        span = trace.get_current_span()
        if span.is_recording():
            span.set_attributes(
                {
                    "db.table": "cached_media",
                    "db.operation": "select",
                    "tmdb.series_id": tmdb_series_id,
                    "media.season": season,
                    "media.episode": episode,
                }
            )

        try:
            self._logger.debug(
                f"Getting cached TV episode by Series ID: {tmdb_series_id}, Season: {season}, Episode: {episode}"
            )
            with self._get_connection() as conn, conn.cursor(row_factory=dict_row) as cursor:
                cursor.execute(
                    "SELECT * FROM cached_media "
                    "WHERE media_type = %s AND tmdb_series_id = %s AND season = %s AND episode = %s "
                    "ORDER BY modified_at DESC LIMIT 1;",
                    (TV, tmdb_series_id, season, episode),
                )
                return cursor.fetchone()
        except psycopg.Error as e:
            raise RuntimeError(f"Error getting cached TV episode: {e}") from e

    @_logger.trace("cache_data")
    def cache_data(self, new_record: MediaData) -> MediaData:
        """Insert a record into the cache, or return the row already cached under the same TMDB id and media type.

        Only keys listed in :data:`CACHE_COLUMNS` are written; the ``used_*`` flags default to False.

        Args:
            new_record: The media record to store.

        Returns:
            The record with the ``id`` the database assigned, or the existing row when another request cached the
            same media first.

        Raises:
            ValueError: If a NOT NULL column has no value.
            RuntimeError: If the insert fails (including a TV record keyed by its series id, which the table rejects).
        """
        span = trace.get_current_span()
        if span.is_recording():
            span.set_attributes({"db.table": "cached_media", "db.operation": "insert"})

        if not self.is_cacheable(new_record):
            raise ValueError("Missing required fields in the record")

        columns = [column for column in CACHE_COLUMNS if column in new_record]
        values = [
            bool(new_record[column]) if column in _SERVICE_FLAG_COLUMNS else new_record[column] for column in columns
        ]
        query = sql.SQL(
            "INSERT INTO cached_media ({columns}) VALUES ({placeholders}) "
            "ON CONFLICT (tmdb_id, media_type) DO NOTHING RETURNING id;"
        ).format(
            columns=sql.SQL(", ").join(sql.Identifier(column) for column in columns),
            placeholders=sql.SQL(", ").join(sql.Placeholder() * len(columns)),
        )

        try:
            self._logger.debug(f"Caching record with title: {new_record.get('title', '[Unknown]')!r}")
            with self._get_connection() as conn, conn.cursor(row_factory=dict_row) as cursor:
                cursor.execute(query, values)
                inserted = cursor.fetchone()
        except psycopg.Error as e:
            raise RuntimeError(f"Error caching record: {e}") from e

        if inserted is not None:
            self._logger.debug(f"Record cached with ID: {inserted['id']}")
            return {**new_record, "id": str(inserted["id"])}

        existing = self.get_cached_by_tmdb_id(new_record["tmdb_id"], new_record["media_type"])
        if existing is None:
            raise RuntimeError("Error caching record: the insert conflicted but no cached row was found")

        self._logger.debug(f"Record was cached concurrently with ID: {existing['id']}")
        return {**existing, "id": str(existing["id"])}

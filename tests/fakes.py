"""Hand-rolled test doubles shared by the unit tests."""

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any, Self, cast

from src.converters.create_searchable_reference import create_searchable_reference
from src.models.media_info import MediaData
from src.repositories.base_repository import PoolGetter
from src.repositories.media_info_cache import MediaInfoCache
from src.repositories.request_logger import RequestLogger


class FakeCursor:
    """Records executed statements and the row factory each cursor was opened with; returns queued rows."""

    def __init__(self, rows: list[Any] | None = None, error: Exception | None = None) -> None:
        self.executed: list[tuple[Any, Any]] = []
        self.row_factories: list[Any] = []
        self._rows = list(rows or [])
        self._error = error

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc_info: object) -> None:
        return None

    def execute(self, query: Any, params: Any = None) -> None:
        self.executed.append((query, params))
        if self._error is not None:
            raise self._error

    def fetchone(self) -> Any:
        return self._rows.pop(0) if self._rows else None

    def fetchall(self) -> list[Any]:
        rows, self._rows = self._rows, []
        return rows


class FakeConnection:
    """Hands out one shared cursor."""

    def __init__(self, cursor: FakeCursor) -> None:
        self._cursor = cursor

    def cursor(self, row_factory: Any = None) -> FakeCursor:
        self._cursor.row_factories.append(row_factory)
        return self._cursor


class FakePool:
    """Stands in for a psycopg ConnectionPool; every connection shares one cursor."""

    def __init__(self, rows: list[Any] | None = None, error: Exception | None = None) -> None:
        self.cursor = FakeCursor(rows, error)

    @contextmanager
    def connection(self) -> Iterator[FakeConnection]:
        yield FakeConnection(self.cursor)

    def getter(self) -> PoolGetter:
        return cast(PoolGetter, lambda: self)


def no_pool() -> Any:
    """A pool getter for doubles that must never reach the database."""
    raise AssertionError("This test double must not open a database connection.")


class InMemoryCache(MediaInfoCache):
    """MediaInfoCache backed by a list; lookups mirror the SQL filters of the real repository.

    Args:
        records: Rows already cached.
        ignore_media_type: Make the lookups ignore ``media_type``, to exercise the guards against cache hits of
            another media type.
    """

    def __init__(self, records: list[MediaData] | None = None, ignore_media_type: bool = False) -> None:
        super().__init__(pool_getter=no_pool)
        self.records: list[MediaData] = list(records or [])
        self.inserted: list[MediaData] = []
        self._ignore_media_type = ignore_media_type

    def _type_matches(self, record: MediaData, media_type: str) -> bool:
        return self._ignore_media_type or record.get("media_type") == media_type

    def get_cached_by_obj(self, obj: MediaData | None) -> MediaData | None:
        if obj is None or obj.get("title") is None:
            return None
        title = str(obj["title"]).lower()
        references = {
            str(reference).lower()
            for reference in (create_searchable_reference(str(obj["title"])), obj.get("searchable_reference"))
            if reference
        }
        for record in self.records:
            title_matches = str(record.get("title", "")).lower() == title
            reference_matches = str(record.get("searchable_reference") or "").lower() in references
            if not (title_matches or reference_matches) or not self._type_matches(record, obj["media_type"]):
                continue
            if obj["media_type"] == "tv" and (record.get("season"), record.get("episode")) != (
                obj.get("season"),
                obj.get("episode"),
            ):
                continue
            return record
        return None

    def get_cached_by_id(self, media_id: str) -> MediaData | None:
        return next((r for r in self.records if str(r.get("id")) == media_id), None)

    def get_cached_by_tmdb_id(self, tmdb_id: int, media_type: str) -> MediaData | None:
        return next(
            (r for r in self.records if r.get("tmdb_id") == tmdb_id and self._type_matches(r, media_type)), None
        )

    def get_cached_tv_episode(self, tmdb_series_id: int, season: int, episode: int) -> MediaData | None:
        return next(
            (
                r
                for r in self.records
                if self._type_matches(r, "tv")
                and r.get("tmdb_series_id") == tmdb_series_id
                and r.get("season") == season
                and r.get("episode") == episode
            ),
            None,
        )

    def cache_data(self, new_record: MediaData) -> MediaData:
        stored = {**new_record, "id": f"cached-{len(self.records) + 1}"}
        self.records.append(stored)
        self.inserted.append(stored)
        return stored


class RecordingRequestLogger(RequestLogger):
    """RequestLogger that keeps requests in memory."""

    def __init__(self) -> None:
        super().__init__(pool_getter=no_pool)
        self.started: list[tuple[str, str, str]] = []
        self.completed: list[dict[str, Any]] = []

    def log_start(self, endpoint: str, filename: str, requester_ip: str) -> str:
        self.started.append((endpoint, filename, requester_ip))
        return f"request-{len(self.started)}"

    def log_completed(
        self,
        request_id: str,
        status_code: int,
        result_media_id: str | None = None,
        error_message: str | None = None,
        outcome: str | None = None,
        decided_by: str | None = None,
    ) -> None:
        self.completed.append(
            {
                "request_id": request_id,
                "status_code": status_code,
                "result_media_id": result_media_id,
                "error_message": error_message,
                "outcome": outcome,
                "decided_by": decided_by,
            }
        )

    def get_recent_requests(self, limit: int = 100) -> list[dict[str, Any]]:
        return [
            {
                "id": entry["request_id"],
                "result_status": entry["status_code"],
                "result_media_id": entry["result_media_id"],
                "error_message": entry["error_message"],
                "outcome": entry["outcome"],
                "decided_by": entry["decided_by"],
            }
            for entry in reversed(self.completed[-limit:])
        ]

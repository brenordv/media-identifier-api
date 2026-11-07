import logging
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from opentelemetry.instrumentation.psycopg import PsycopgInstrumentor

import main
from main import app, get_media_identifier
from src.database.migrations import MigrationError
from src.media_identifiers.media_identifier import MediaIdentifier
from src.media_identifiers.pipeline.base import PipelineExecutionError
from src.models.media_info import MediaData
from src.repositories.repository_factory import get_cache_repository, get_request_logger
from tests.fakes import InMemoryCache, RecordingRequestLogger

SLOW_HORSES_FILE = "/watch/Slow.Horses.S06E06.Judgment.Day.1080p.ATVP.WEB-DL.DDP5.1.H.264-NTb.mkv"
SECRET_IN_ERROR = "connection failed: password=hunter2 host=db.internal"


class StubIdentifier(MediaIdentifier):
    def __init__(self, result: MediaData | None = None, error: Exception | None = None) -> None:
        super().__init__(InMemoryCache())
        self._result = result
        self._error = error
        self.filenames: list[str] = []

    def get_media_info_by_filename(self, file_path: str) -> MediaData | None:
        self.filenames.append(file_path)
        if self._error is not None:
            raise self._error
        return self._result

    def get_media_info(
        self, media_type: str, year: int, title: str, season: int | None, episode: int | None
    ) -> MediaData | None:
        if self._error is not None:
            raise self._error
        return self._result


@pytest.fixture
def request_logger() -> RecordingRequestLogger:
    return RecordingRequestLogger()


@pytest.fixture
def cache() -> InMemoryCache:
    return InMemoryCache()


@contextmanager
def _client(
    request_logger: RecordingRequestLogger, cache: InMemoryCache, identifier: MediaIdentifier
) -> Iterator[TestClient]:
    app.dependency_overrides[get_request_logger] = lambda: request_logger
    app.dependency_overrides[get_cache_repository] = lambda: cache
    app.dependency_overrides[get_media_identifier] = lambda: identifier
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides = {}


@pytest.fixture
def identified_client(request_logger: RecordingRequestLogger, cache: InMemoryCache) -> Iterator[TestClient]:
    identifier = StubIdentifier(result={"id": "cached-1", "title": "Slow Horses", "media_type": "tv", "season": 6})
    with _client(request_logger, cache, identifier) as client:
        yield client


@pytest.fixture
def empty_client(request_logger: RecordingRequestLogger, cache: InMemoryCache) -> Iterator[TestClient]:
    with _client(request_logger, cache, StubIdentifier(result=None)) as client:
        yield client


@pytest.fixture
def failing_client(request_logger: RecordingRequestLogger, cache: InMemoryCache) -> Iterator[TestClient]:
    with _client(request_logger, cache, StubIdentifier(error=RuntimeError(SECRET_IN_ERROR))) as client:
        yield client


def test_app_registers_every_endpoint() -> None:
    paths = {route.path for route in app.routes if isinstance(route, APIRoute)}

    assert paths == {
        "/api/guess",
        "/api/media-info",
        "/api/media-info/{media_id}",
        "/api/health",
        "/api/statistics",
    }


def test_importing_main_instruments_psycopg() -> None:
    assert PsycopgInstrumentor().is_instrumented_by_opentelemetry


def test_health_check_returns_healthy(empty_client: TestClient) -> None:
    response = empty_client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"message": "healthy"}


def test_guess_without_filename_returns_400(empty_client: TestClient) -> None:
    response = empty_client.get("/api/guess")

    assert response.status_code == 400


def test_guess_with_overlong_filename_returns_422(empty_client: TestClient) -> None:
    response = empty_client.get("/api/guess", params={"it": "a" * 1025})

    assert response.status_code == 422


def test_guess_identified_media_returns_200_and_records_result(
    identified_client: TestClient, request_logger: RecordingRequestLogger
) -> None:
    response = identified_client.get("/api/guess", params={"it": SLOW_HORSES_FILE})

    assert response.status_code == 200
    assert response.json()["title"] == "Slow Horses"
    assert request_logger.started == [("/api/guess", SLOW_HORSES_FILE, "testclient")]
    assert request_logger.completed[-1]["status_code"] == 200
    assert request_logger.completed[-1]["result_media_id"] == "cached-1"


def test_guess_unidentified_media_returns_204(empty_client: TestClient, request_logger: RecordingRequestLogger) -> None:
    response = empty_client.get("/api/guess", params={"it": "readme.txt"})

    assert response.status_code == 204
    assert request_logger.completed[-1]["status_code"] == 204


def test_guess_failure_returns_generic_500_and_logs_the_exception(
    failing_client: TestClient, request_logger: RecordingRequestLogger, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.ERROR):
        response = failing_client.get("/api/guess", params={"it": SLOW_HORSES_FILE})

    assert response.status_code == 500
    assert "hunter2" not in response.text
    assert request_logger.completed[-1]["status_code"] == 500
    assert "hunter2" not in (request_logger.completed[-1]["error_message"] or "")
    assert "RuntimeError" in request_logger.completed[-1]["error_message"]
    assert any(record.exc_info and "request-1" in record.getMessage() for record in caplog.records)


def test_statistics_never_exposes_exception_text(failing_client: TestClient) -> None:
    failing_client.get("/api/guess", params={"it": SLOW_HORSES_FILE})

    response = failing_client.get("/api/statistics")

    assert response.status_code == 200
    assert response.json()[0]["result_status"] == 500
    assert "hunter2" not in response.text


@pytest.mark.parametrize("num_requests", [0, -5, 1001])
def test_statistics_out_of_range_count_returns_422(empty_client: TestClient, num_requests: int) -> None:
    response = empty_client.get("/api/statistics", params={"num_requests": num_requests})

    assert response.status_code == 422


@pytest.mark.parametrize(
    "params",
    [
        {"media_type": "movie", "title": "Possessed"},
        {"media_type": "podcast", "title": "Possessed", "year": 2000},
        {"media_type": "tv", "title": "Slow Horses", "year": 2022, "episode": 1},
        {"media_type": "tv", "title": "Slow Horses", "year": 2022, "season": 1},
        {"media_type": "movie", "title": "Possessed", "year": 1899},
        {"media_type": "movie", "title": "Possessed", "year": datetime.now().year + 1},
    ],
)
def test_media_info_invalid_parameters_return_400(empty_client: TestClient, params: dict[str, str | int]) -> None:
    response = empty_client.get("/api/media-info", params=params)

    assert response.status_code == 400


def test_media_info_identified_movie_returns_200(identified_client: TestClient) -> None:
    response = identified_client.get(
        "/api/media-info", params={"media_type": "movie", "title": "Possessed", "year": 2000}
    )

    assert response.status_code == 200


def test_media_info_by_unknown_id_returns_404(empty_client: TestClient, request_logger: RecordingRequestLogger) -> None:
    response = empty_client.get(f"/api/media-info/{uuid4()}")

    assert response.status_code == 404
    assert request_logger.completed[-1]["status_code"] == 404


def test_media_info_by_known_id_returns_the_record(empty_client: TestClient, cache: InMemoryCache) -> None:
    media_id = str(uuid4())
    cache.records.append({"id": media_id, "title": "Possessed", "media_type": "movie"})

    response = empty_client.get(f"/api/media-info/{media_id}")

    assert response.status_code == 200
    assert response.json()["id"] == media_id


class FailingCache(InMemoryCache):
    def get_cached_by_id(self, media_id: str) -> MediaData | None:
        raise RuntimeError(SECRET_IN_ERROR)


class FailingRequestHistory(RecordingRequestLogger):
    def __init__(self) -> None:
        super().__init__()
        self.requested_limits: list[int] = []

    def get_recent_requests(self, limit: int = 100) -> list[dict[str, object]]:
        self.requested_limits.append(limit)
        raise RuntimeError(SECRET_IN_ERROR)


class RetryingIdentifier(StubIdentifier):
    def get_media_info_by_filename(self, file_path: str) -> MediaData | None:
        self.filenames.append(file_path)
        if len(self.filenames) == 1:
            raise PipelineExecutionError("Handler 'tmdb_identify_series' execution failed")
        return {"id": "cached-2", "title": "Slow Horses", "media_type": "tv"}


def test_guess_pipeline_failure_retries_with_the_file_name_only(
    request_logger: RecordingRequestLogger, cache: InMemoryCache
) -> None:
    identifier = RetryingIdentifier()
    with _client(request_logger, cache, identifier) as client:
        response = client.get("/api/guess", params={"it": SLOW_HORSES_FILE})

    assert response.status_code == 200
    assert identifier.filenames == [
        SLOW_HORSES_FILE.lower(),
        "slow.horses.s06e06.judgment.day.1080p.atvp.web-dl.ddp5.1.h.264-ntb.mkv",
    ]


def test_media_info_failure_returns_generic_500(
    failing_client: TestClient, request_logger: RecordingRequestLogger
) -> None:
    response = failing_client.get("/api/media-info", params={"media_type": "movie", "title": "Possessed", "year": 2000})

    assert response.status_code == 500
    assert "hunter2" not in response.text
    assert request_logger.completed[-1]["status_code"] == 500


def test_media_info_by_id_lookup_failure_returns_generic_500(request_logger: RecordingRequestLogger) -> None:
    with _client(request_logger, FailingCache(), StubIdentifier()) as client:
        response = client.get(f"/api/media-info/{uuid4()}")

    assert response.status_code == 500
    assert "hunter2" not in response.text
    assert request_logger.completed[-1]["status_code"] == 500


def test_statistics_lookup_failure_returns_generic_500(cache: InMemoryCache) -> None:
    request_history = FailingRequestHistory()
    with _client(request_history, cache, StubIdentifier()) as client:
        response = client.get("/api/statistics")

    assert response.status_code == 500
    assert "hunter2" not in response.text
    assert request_history.requested_limits == [100]


def test_lifespan_migrates_then_opens_the_pool_and_closes_it_on_shutdown(monkeypatch: pytest.MonkeyPatch) -> None:
    events: list[str] = []
    monkeypatch.setattr(main, "build_pool_config", lambda: SimpleNamespace(conn_info="conninfo"))
    monkeypatch.setattr(main, "apply_migrations", lambda conninfo, logger: events.append(f"migrate:{conninfo}"))
    monkeypatch.setattr(main, "create_pool", lambda config: events.append("create_pool"))
    monkeypatch.setattr(main, "close_pool", lambda: events.append("close_pool"))

    with TestClient(app):
        events.append("serving")

    assert events == ["migrate:conninfo", "create_pool", "serving", "close_pool"]


def test_lifespan_migration_failure_stops_startup_before_opening_the_pool(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    events: list[str] = []

    def failing_migrations(conninfo: str, logger: object) -> None:
        raise MigrationError("Migration 0003_remove_tv_rows_keyed_by_series_id failed and was rolled back")

    monkeypatch.setattr(main, "build_pool_config", lambda: SimpleNamespace(conn_info="conninfo"))
    monkeypatch.setattr(main, "apply_migrations", failing_migrations)
    monkeypatch.setattr(main, "create_pool", lambda config: events.append("create_pool"))
    monkeypatch.setattr(main, "close_pool", lambda: events.append("close_pool"))

    with caplog.at_level(logging.ERROR), pytest.raises(MigrationError):
        with TestClient(app):
            pass

    assert events == []
    assert any(record.exc_info and "migrations failed" in record.getMessage() for record in caplog.records)

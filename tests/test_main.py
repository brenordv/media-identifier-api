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
from main import INTERNAL_ERROR_DETAIL, SERVICE_UNAVAILABLE_DETAIL, app, get_media_identifier
from src import secret_store
from src.database.migrations import MigrationError
from src.media_identifiers.errors import UpstreamUnavailableError
from src.media_identifiers.media_identifier import IdentificationResult, MediaIdentifier
from src.media_identifiers.pipeline import DecidedBy, IdentificationOutcome
from src.media_identifiers.pipeline.base import PipelineExecutionError
from src.models.media_info import MediaData
from src.repositories.repository_factory import get_cache_repository, get_request_logger
from src.secret_store import SecretsError
from tests.fakes import InMemoryCache, RecordingRequestLogger

SLOW_HORSES_FILE = "/watch/Slow.Horses.S06E06.Judgment.Day.1080p.ATVP.WEB-DL.DDP5.1.H.264-NTb.mkv"
SLOW_HORSES_BARE_NAME = "slow.horses.s06e06.judgment.day.1080p.atvp.web-dl.ddp5.1.h.264-ntb.mkv"
SECRET_IN_ERROR = "connection failed: password=hunter2 host=db.internal"

UNIDENTIFIED = IdentificationResult(None, IdentificationOutcome.UNIDENTIFIED)
NOT_MEDIA = IdentificationResult(None, IdentificationOutcome.NOT_MEDIA, "nimble")


def identified(media: MediaData, decided_by: DecidedBy = "guessit") -> IdentificationResult:
    return IdentificationResult(media, IdentificationOutcome.IDENTIFIED, decided_by)


class StubIdentifier(MediaIdentifier):
    """Answers with the given outcomes in order (the last one repeats) and records what it was asked."""

    def __init__(self, *outcomes: IdentificationResult | Exception) -> None:
        super().__init__(InMemoryCache())
        self._outcomes = list(outcomes) or [UNIDENTIFIED]
        self.filenames: list[str] = []
        self.metadata_lookups: list[tuple[str, int, str, int | None, int | None]] = []

    def _next(self) -> IdentificationResult:
        outcome = self._outcomes.pop(0) if len(self._outcomes) > 1 else self._outcomes[0]
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    def get_media_info_by_filename(self, file_path: str) -> IdentificationResult:
        self.filenames.append(file_path)
        return self._next()

    def get_media_info(
        self, media_type: str, year: int, title: str, season: int | None, episode: int | None
    ) -> IdentificationResult:
        self.metadata_lookups.append((media_type, year, title, season, episode))
        return self._next()


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
    identifier = StubIdentifier(identified({"id": "cached-1", "title": "Slow Horses", "media_type": "tv", "season": 6}))
    with _client(request_logger, cache, identifier) as client:
        yield client


@pytest.fixture
def empty_client(request_logger: RecordingRequestLogger, cache: InMemoryCache) -> Iterator[TestClient]:
    with _client(request_logger, cache, StubIdentifier(UNIDENTIFIED)) as client:
        yield client


@pytest.fixture
def failing_client(request_logger: RecordingRequestLogger, cache: InMemoryCache) -> Iterator[TestClient]:
    with _client(request_logger, cache, StubIdentifier(RuntimeError(SECRET_IN_ERROR))) as client:
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


def test_guess_identified_media_returns_200_and_records_the_outcome(
    identified_client: TestClient, request_logger: RecordingRequestLogger
) -> None:
    response = identified_client.get("/api/guess", params={"it": SLOW_HORSES_FILE})

    assert response.status_code == 200
    assert response.json()["title"] == "Slow Horses"
    assert request_logger.started == [("/api/guess", SLOW_HORSES_FILE, "testclient")]
    completed = request_logger.completed[-1]
    assert (completed["status_code"], completed["result_media_id"]) == (200, "cached-1")
    assert (completed["outcome"], completed["decided_by"]) == ("identified", "guessit")


def test_guess_unidentified_media_returns_204_flagged_for_review(
    empty_client: TestClient, request_logger: RecordingRequestLogger
) -> None:
    response = empty_client.get("/api/guess", params={"it": "readme.txt"})

    assert response.status_code == 204
    completed = request_logger.completed[-1]
    assert (completed["status_code"], completed["outcome"], completed["decided_by"]) == (204, "unidentified", None)


def test_guess_not_media_returns_204_without_retrying_the_bare_name(
    request_logger: RecordingRequestLogger, cache: InMemoryCache
) -> None:
    identifier = StubIdentifier(NOT_MEDIA)
    with _client(request_logger, cache, identifier) as client:
        response = client.get("/api/guess", params={"it": "/watch/Retro/NES/Balloon Fight (JU) [o5].nes"})

    assert response.status_code == 204
    assert len(identifier.filenames) == 1
    completed = request_logger.completed[-1]
    assert (completed["outcome"], completed["decided_by"]) == ("not_media", "nimble")


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


def test_guess_needing_an_unavailable_service_returns_503_with_the_cause_stored(
    request_logger: RecordingRequestLogger, cache: InMemoryCache, caplog: pytest.LogCaptureFixture
) -> None:
    identifier = StubIdentifier(UpstreamUnavailableError("openai", "rate_limited", "credit_balance_exhausted"))
    with _client(request_logger, cache, identifier) as client, caplog.at_level(logging.WARNING):
        response = client.get("/api/guess", params={"it": SLOW_HORSES_FILE})

    assert response.status_code == 503
    assert response.json() == {"detail": SERVICE_UNAVAILABLE_DETAIL}
    assert len(identifier.filenames) == 1
    completed = request_logger.completed[-1]
    assert completed["status_code"] == 503
    assert completed["error_message"] == f"{SERVICE_UNAVAILABLE_DETAIL} (openai: rate_limited credit_balance_exhausted)"
    assert completed["outcome"] is None
    warnings = [record for record in caplog.records if "unavailable service" in record.getMessage()]
    assert [(record.levelno, record.exc_info) for record in warnings] == [(logging.WARNING, None)]


def test_guess_unidentified_from_the_full_path_retries_with_the_file_name_only(
    request_logger: RecordingRequestLogger, cache: InMemoryCache
) -> None:
    identifier = StubIdentifier(UNIDENTIFIED, identified({"id": "cached-2", "title": "Slow Horses"}))
    with _client(request_logger, cache, identifier) as client:
        response = client.get("/api/guess", params={"it": SLOW_HORSES_FILE})

    assert response.status_code == 200
    assert identifier.filenames == [SLOW_HORSES_FILE.lower(), SLOW_HORSES_BARE_NAME]


def test_guess_unidentified_bare_file_name_is_not_retried(
    request_logger: RecordingRequestLogger, cache: InMemoryCache
) -> None:
    identifier = StubIdentifier(UNIDENTIFIED)
    with _client(request_logger, cache, identifier) as client:
        client.get("/api/guess", params={"it": "readme.txt"})

    assert identifier.filenames == ["readme.txt"]


def test_guess_pipeline_error_returns_generic_500_without_retrying(
    request_logger: RecordingRequestLogger, cache: InMemoryCache
) -> None:
    identifier = StubIdentifier(PipelineExecutionError("Handler 'tmdb_identify_series' execution failed"))
    with _client(request_logger, cache, identifier) as client:
        response = client.get("/api/guess", params={"it": SLOW_HORSES_FILE})

    assert response.status_code == 500
    assert len(identifier.filenames) == 1


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


class StoredRequestHistory(RecordingRequestLogger):
    def get_recent_requests(self, limit: int = 100) -> list[dict[str, object]]:
        return [
            {"id": "1x-row", "result_status": 500, "error_message": f"Error processing filename: {SECRET_IN_ERROR}"},
            {"id": "bare-500", "result_status": 500, "error_message": INTERNAL_ERROR_DETAIL},
            {"id": "class-500", "result_status": 500, "error_message": f"{INTERNAL_ERROR_DETAIL} (RuntimeError)"},
            {"id": "padded-500", "result_status": 500, "error_message": f"{INTERNAL_ERROR_DETAIL} {SECRET_IN_ERROR}"},
            {
                "id": "shaped-503",
                "result_status": 503,
                "error_message": f"{SERVICE_UNAVAILABLE_DETAIL} (tmdb: timeout)",
                "outcome": None,
            },
            {
                "id": "padded-503",
                "result_status": 503,
                "error_message": f"{SERVICE_UNAVAILABLE_DETAIL} (tmdb: timeout) {SECRET_IN_ERROR}",
            },
            {
                "id": "coded-503",
                "result_status": 503,
                "error_message": f"{SERVICE_UNAVAILABLE_DETAIL} (openai: rate_limited credit_balance_exhausted)",
            },
            {"id": "odd-503", "result_status": 503, "error_message": f"{SERVICE_UNAVAILABLE_DETAIL} (tmdb: exploded)"},
            {"id": "not-found", "result_status": 404, "error_message": "Media not found"},
            {"id": "flagged", "result_status": 204, "error_message": None, "outcome": "unidentified"},
        ]


def test_statistics_keeps_only_the_message_shapes_this_api_writes(cache: InMemoryCache) -> None:
    with _client(StoredRequestHistory(), cache, StubIdentifier()) as client:
        response = client.get("/api/statistics")

    entries = {entry["id"]: entry for entry in response.json()}
    assert {row_id: entry["error_message"] for row_id, entry in entries.items()} == {
        "1x-row": INTERNAL_ERROR_DETAIL,
        "bare-500": INTERNAL_ERROR_DETAIL,
        "class-500": f"{INTERNAL_ERROR_DETAIL} (RuntimeError)",
        "padded-500": INTERNAL_ERROR_DETAIL,
        "shaped-503": f"{SERVICE_UNAVAILABLE_DETAIL} (tmdb: timeout)",
        "padded-503": SERVICE_UNAVAILABLE_DETAIL,
        "coded-503": f"{SERVICE_UNAVAILABLE_DETAIL} (openai: rate_limited credit_balance_exhausted)",
        "odd-503": SERVICE_UNAVAILABLE_DETAIL,
        "not-found": "Media not found",
        "flagged": None,
    }
    assert entries["flagged"]["outcome"] == "unidentified"


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


def test_media_info_identified_movie_returns_200_and_records_the_validated_query(
    request_logger: RecordingRequestLogger, cache: InMemoryCache
) -> None:
    identifier = StubIdentifier(identified({"id": "cached-1", "title": "Possessed", "media_type": "movie"}, "request"))
    with _client(request_logger, cache, identifier) as client:
        response = client.get(
            "/api/media-info", params={"media_type": "Film", "title": "Possessed", "year": 2000, "extra": "x" * 500}
        )

    assert response.status_code == 200
    assert identifier.metadata_lookups == [("movie", 2000, "Possessed", None, None)]
    assert request_logger.started[0][1] == "media_type=movie&title=Possessed&year=2000"
    assert (request_logger.completed[-1]["outcome"], request_logger.completed[-1]["decided_by"]) == (
        "identified",
        "request",
    )


def test_media_info_tv_special_passes_season_zero_and_episode(
    request_logger: RecordingRequestLogger, cache: InMemoryCache
) -> None:
    identifier = StubIdentifier(identified({"id": "cached-2", "title": "Slow Horses", "media_type": "tv"}))
    with _client(request_logger, cache, identifier) as client:
        response = client.get(
            "/api/media-info",
            params={"media_type": "series", "title": "Slow Horses", "year": 2022, "season": 0, "episode": 1},
        )

    assert response.status_code == 200
    assert identifier.metadata_lookups == [("tv", 2022, "Slow Horses", 0, 1)]


def test_media_info_with_tmdb_unavailable_returns_503(
    request_logger: RecordingRequestLogger, cache: InMemoryCache
) -> None:
    identifier = StubIdentifier(UpstreamUnavailableError("tmdb", "server_error"))
    with _client(request_logger, cache, identifier) as client:
        response = client.get("/api/media-info", params={"media_type": "movie", "title": "Possessed", "year": 2000})

    assert response.status_code == 503
    assert response.json() == {"detail": SERVICE_UNAVAILABLE_DETAIL}
    completed = request_logger.completed[-1]
    assert completed["error_message"] == f"{SERVICE_UNAVAILABLE_DETAIL} (tmdb: server_error)"
    assert completed["outcome"] is None


def test_media_info_without_a_match_returns_204_flagged_for_review(
    empty_client: TestClient, request_logger: RecordingRequestLogger
) -> None:
    response = empty_client.get("/api/media-info", params={"media_type": "movie", "title": "Possessed", "year": 2000})

    assert response.status_code == 204
    completed = request_logger.completed[-1]
    assert (completed["outcome"], completed["decided_by"]) == ("unidentified", None)


@pytest.mark.parametrize(("season", "episode"), [(-1, 1), (1, 0), (10000, 1), (1, 10000)])
def test_media_info_out_of_range_season_or_episode_returns_422(
    empty_client: TestClient, season: int, episode: int
) -> None:
    response = empty_client.get(
        "/api/media-info",
        params={"media_type": "tv", "title": "Slow Horses", "year": 2022, "season": season, "episode": episode},
    )

    assert response.status_code == 422


def test_media_info_by_unknown_id_returns_404(empty_client: TestClient, request_logger: RecordingRequestLogger) -> None:
    response = empty_client.get(f"/api/media-info/{uuid4()}")

    assert response.status_code == 404
    assert request_logger.completed[-1]["status_code"] == 404


def test_media_info_by_known_id_returns_the_record_without_an_outcome(
    empty_client: TestClient, cache: InMemoryCache, request_logger: RecordingRequestLogger
) -> None:
    media_id = str(uuid4())
    cache.records.append({"id": media_id, "title": "Possessed", "media_type": "movie"})

    response = empty_client.get(f"/api/media-info/{media_id}")

    assert response.status_code == 200
    assert response.json()["id"] == media_id
    assert request_logger.completed[-1]["outcome"] is None


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


def _record_lifespan(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    events: list[str] = []
    monkeypatch.setattr(main, "build_pool_config", lambda: SimpleNamespace(conn_info="conninfo"))
    monkeypatch.setattr(main, "apply_migrations", lambda conninfo, logger: events.append(f"migrate:{conninfo}"))
    monkeypatch.setattr(main, "create_pool", lambda config: events.append("create_pool"))
    monkeypatch.setattr(main, "close_pool", lambda: events.append("close_pool"))
    return events


def _settings_failure_logged(caplog: pytest.LogCaptureFixture) -> bool:
    return any(record.exc_info and "Reading the settings failed" in record.getMessage() for record in caplog.records)


def test_lifespan_migrates_then_opens_the_pool_and_closes_it_on_shutdown(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture, secret_values: dict[str, str]
) -> None:
    secret_values["MEDIA_IDENTIFIER_TMDB_API_KEY"] = "tmdb-token"
    events = _record_lifespan(monkeypatch)

    with caplog.at_level(logging.INFO), TestClient(app):
        events.append("serving")

    assert events == ["migrate:conninfo", "create_pool", "serving", "close_pool"]
    messages = [record.getMessage() for record in caplog.records]
    assert any("MEDIA_IDENTIFIER_NIMBLE_URL is not set in Infisical" in message for message in messages)
    assert any("MEDIA_IDENTIFIER_OPENAI_API_KEY is not set in Infisical" in message for message in messages)


def test_lifespan_reads_every_setting_at_startup(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    settings = {
        "MEDIA_IDENTIFIER_NIMBLE_URL": "http://nimble.example:11434",
        "MEDIA_IDENTIFIER_OPENAI_API_KEY": "sk-test",
        "MEDIA_IDENTIFIER_OPENAI_ORGANIZATION": "org-media",
        "MEDIA_IDENTIFIER_TMDB_API_KEY": "tmdb-token",
        "MEDIA_IDENTIFIER_POSTGRES_CONNECTION_STRING": "postgresql://media:s3cret@db.example:5433/media_cache",
    }
    requested: list[str] = []

    def recording_fetch(name: str) -> str | None:
        requested.append(name)
        return settings.get(name)

    monkeypatch.setattr(secret_store, "_default_store", secret_store.SecretStore(recording_fetch, "Infisical at test"))
    monkeypatch.setattr(main, "apply_migrations", lambda conninfo, logger: None)
    monkeypatch.setattr(main, "create_pool", lambda config: None)
    monkeypatch.setattr(main, "close_pool", lambda: None)

    with caplog.at_level(logging.INFO), TestClient(app):
        pass

    assert sorted(requested) == sorted(settings)
    assert any("Reading the settings from Infisical at test" in record.getMessage() for record in caplog.records)


def test_lifespan_without_tmdb_key_stops_startup_before_migrating(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    events = _record_lifespan(monkeypatch)

    with caplog.at_level(logging.ERROR), pytest.raises(SecretsError, match="MEDIA_IDENTIFIER_TMDB_API_KEY"):
        with TestClient(app):
            pass

    assert events == []
    assert _settings_failure_logged(caplog)


def test_lifespan_invalid_nimble_url_stops_startup_before_migrating(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture, secret_values: dict[str, str]
) -> None:
    events = _record_lifespan(monkeypatch)
    secret_values.update(
        {"MEDIA_IDENTIFIER_NIMBLE_URL": "ftp://nimble.example", "MEDIA_IDENTIFIER_TMDB_API_KEY": "tmdb-token"}
    )

    with caplog.at_level(logging.ERROR), pytest.raises(ValueError, match="MEDIA_IDENTIFIER_NIMBLE_URL"):
        with TestClient(app):
            pass

    assert events == []
    assert _settings_failure_logged(caplog)


def test_lifespan_migration_failure_stops_startup_before_opening_the_pool(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture, secret_values: dict[str, str]
) -> None:
    secret_values["MEDIA_IDENTIFIER_TMDB_API_KEY"] = "tmdb-token"
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

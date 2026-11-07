"""HTTP API: identify media from a file name or from known metadata, and report on past requests."""

from dotenv import load_dotenv

load_dotenv()

import re
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from functools import cache
from pathlib import Path
from typing import Annotated, Any, get_args
from urllib.parse import urlencode
from uuid import UUID

from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response, status
from fastapi.responses import JSONResponse
from opentelemetry import trace
from raccoontools_db import close_pool, create_pool

from src.database.migrations import apply_migrations
from src.database.pool import build_pool_config
from src.media_identifiers.errors import UpstreamReason, UpstreamService, UpstreamUnavailableError
from src.media_identifiers.media_identifier import IdentificationResult, MediaIdentifier
from src.media_identifiers.media_type_helpers import is_tv, normalize_media_type
from src.media_identifiers.nimble_classifier import get_nimble_url
from src.media_identifiers.openai_identifier import is_openai_configured
from src.media_identifiers.pipeline import IdentificationOutcome
from src.media_identifiers.tmdb_identifier import get_tmdb_api_key
from src.models.media_info import MediaData
from src.repositories.media_info_cache import MediaInfoCache
from src.repositories.repository_factory import get_cache_repository, get_request_logger
from src.repositories.request_logger import RequestLogger
from src.secret_store import get_secret_store
from src.utils import flush_all_otel_loggers, get_otel_log_handler, set_request_id

MAX_INPUT_LENGTH = 1024
MAX_SEASON_OR_EPISODE = 9999
MAX_STATISTICS_REQUESTS = 1000
FIRST_ACCEPTED_YEAR = 1900
INTERNAL_ERROR_DETAIL = "Internal error while processing the request."
SERVICE_UNAVAILABLE_DETAIL = "Identification is temporarily unavailable; retry later."

_PUBLIC_500_MESSAGE = re.compile(re.escape(INTERNAL_ERROR_DETAIL) + r"( \([A-Za-z_][A-Za-z0-9_]*\))?")
_PUBLIC_503_MESSAGE = re.compile(
    re.escape(SERVICE_UNAVAILABLE_DETAIL)
    + rf" \(({'|'.join(get_args(UpstreamService))}): ({'|'.join(get_args(UpstreamReason))})( [a-z_]{{1,64}})?\)"
)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Read the settings, migrate the database and open the connection pool; close the pool on shutdown.

    Every Infisical setting is read here, so requests are answered from the cached values.

    Raises:
        SecretsError: If the Infisical bootstrap is incomplete, Infisical cannot be read, or the database connection
            string or the TMDB key is not set.
        ValueError: If ``MEDIA_IDENTIFIER_NIMBLE_URL`` or the database connection string is invalid.
        MigrationError: If a migration cannot be planned or applied.
        psycopg.Error: If connecting to the database fails.
    """
    try:
        logger.info(f"Reading the settings from {get_secret_store().source}")
        if get_nimble_url() is None:
            logger.info("MEDIA_IDENTIFIER_NIMBLE_URL is not set in Infisical; the Nimble triage step is off.")
        if not is_openai_configured():
            logger.info("MEDIA_IDENTIFIER_OPENAI_API_KEY is not set in Infisical; the OpenAI fallback is off.")
        get_tmdb_api_key()
        pool_config = build_pool_config()
    except Exception:
        logger.exception("Reading the settings failed; the API will not start")
        raise

    try:
        apply_migrations(pool_config.conn_info, logger)
    except Exception:
        logger.exception("Applying database migrations failed; the API will not start")
        raise

    create_pool(pool_config)
    try:
        yield
    finally:
        close_pool()


app = FastAPI(
    title="GuessIt API",
    description="API for guessing information from filenames using guessit",
    version="2.0.0",
    lifespan=lifespan,
)

logger = get_otel_log_handler("API", fastapi_app=app)


RequestLoggerDep = Annotated[RequestLogger, Depends(get_request_logger)]
CacheRepositoryDep = Annotated[MediaInfoCache, Depends(get_cache_repository)]


@cache
def get_media_identifier(cache_repository: CacheRepositoryDep) -> MediaIdentifier:
    """Return the media identifier for a cache repository (one instance per repository)."""
    return MediaIdentifier(cache_repository)


MediaIdentifierDep = Annotated[MediaIdentifier, Depends(get_media_identifier)]


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _fail_request(request_logger: RequestLogger, request_id: str, exc: Exception) -> HTTPException:
    """Record a failed request and build the generic 500 sent to the client.

    The response and the stored error message carry only a generic message and the exception class; the exception
    details belong in the log, written before this is called.
    """
    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    request_logger.log_completed(
        request_id, status_code, error_message=f"{INTERNAL_ERROR_DETAIL} ({type(exc).__name__})"
    )
    return HTTPException(status_code=status_code, detail=INTERNAL_ERROR_DETAIL)


def _fail_unavailable(request_logger: RequestLogger, request_id: str, exc: UpstreamUnavailableError) -> HTTPException:
    """Record a request that needed an unavailable service, and build the 503 sent to the client.

    The response carries only the generic message; the stored message adds the service and the reason.
    """
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    request_logger.log_completed(
        request_id, status_code, error_message=f"{SERVICE_UNAVAILABLE_DETAIL} ({exc.cause_label})"
    )
    span = trace.get_current_span()
    if span.is_recording():
        span.set_attributes({"upstream.service": exc.service, "upstream.reason": exc.reason})
    return HTTPException(status_code=status_code, detail=SERVICE_UNAVAILABLE_DETAIL)


def _public_request_entry(entry: dict[str, Any]) -> dict[str, Any]:
    """Return a request history entry safe to show any client.

    A server error keeps its stored message only when it has the exact shape this API writes (the generic text plus
    the exception class, or the 503 text plus the service and reason); anything else, such as exception text
    stored by earlier versions, is replaced with the generic text.
    """
    result_status = entry.get("result_status")
    error_message = entry.get("error_message")
    if result_status is None or result_status < status.HTTP_500_INTERNAL_SERVER_ERROR or not error_message:
        return entry
    if _PUBLIC_500_MESSAGE.fullmatch(error_message) or _PUBLIC_503_MESSAGE.fullmatch(error_message):
        return entry
    if result_status == status.HTTP_503_SERVICE_UNAVAILABLE:
        return {**entry, "error_message": SERVICE_UNAVAILABLE_DETAIL}
    return {**entry, "error_message": INTERNAL_ERROR_DETAIL}


def _record_identification(result: IdentificationResult) -> None:
    span = trace.get_current_span()
    if span.is_recording():
        span.set_attributes(
            {
                "identification.outcome": result.outcome.value,
                "identification.decided_by": result.decided_by or "none",
                "identification.cache_hit": result.cache_hit,
            }
        )


@logger.trace("_prepare_media_info_response")
def _prepare_media_info_response(
    request_logger: RequestLogger,
    media_data: MediaData | None,
    request_id: str,
    identification: IdentificationResult | None = None,
) -> Response:
    outcome = identification.outcome.value if identification else None
    decided_by = identification.decided_by if identification else None
    if not media_data:
        status_code = status.HTTP_204_NO_CONTENT
        request_logger.log_completed(request_id, status_code, None, outcome=outcome, decided_by=decided_by)
        return Response(status_code=status_code)

    status_code = status.HTTP_200_OK
    media_id = media_data.get("id")
    request_logger.log_completed(
        request_id,
        status_code,
        str(media_id) if media_id is not None else None,
        outcome=outcome,
        decided_by=decided_by,
    )

    serializable_result = {
        k: str(v) if not isinstance(v, (str, int, float, bool, list, dict, type(None))) else v
        for k, v in media_data.items()
    }

    return JSONResponse(content=serializable_result, status_code=status_code)


@logger.trace("_sanitize_filename")
def _sanitize_filename(filename: str) -> str:
    _filename = filename.lower()

    if "halcyon" in _filename and not any(x in _filename for x in ["2015", "2026"]):
        return _filename.replace("halcyon", "")

    return _filename


@logger.trace("_process_guess_filename")
def _process_guess_filename(identifier: MediaIdentifier, it: str) -> IdentificationResult:
    """Identify a file name; when the full path leaves it unidentified, try the bare file name once."""
    filename = _sanitize_filename(it)
    result = identifier.get_media_info_by_filename(filename)

    bare_name = Path(filename).name
    if result.outcome == IdentificationOutcome.UNIDENTIFIED and bare_name != filename:
        logger.info(f"Not identified from the full path; retrying with the file name only for: {it!r}")
        return identifier.get_media_info_by_filename(bare_name)

    return result


@app.get("/api/guess")
@logger.trace("/api/guess")
def guess_filename(
    request: Request,
    request_logger: RequestLoggerDep,
    identifier: MediaIdentifierDep,
    it: Annotated[str | None, Query(description="Filename to analyze", max_length=MAX_INPUT_LENGTH)] = None,
) -> Response:
    """Identify the media a file name refers to.

    Returns 200 with the media record; 204 when the file is not a movie or TV release, or nothing could identify
    it; 400 when ``it`` is missing; 503 (generic message) when a service the answer needs is unavailable, so the
    client can retry later; and 500 (generic message) when identification fails otherwise.
    """
    client_ip = _client_ip(request)
    span = trace.get_current_span()
    if span.is_recording():
        span.set_attributes({"http.method": request.method, "http.client_ip": client_ip, "media.input_filename": it})

    if not it:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Filename not provided")

    request_id = request_logger.log_start("/api/guess", it, client_ip)
    set_request_id(request_id)

    try:
        result = _process_guess_filename(identifier, it)
    except UpstreamUnavailableError as exc:
        logger.warning(f"Request {request_id}: identifying {it!r} needs an unavailable service ({exc.cause_label})")
        raise _fail_unavailable(request_logger, request_id, exc) from exc
    except Exception as exc:
        logger.exception(f"Request {request_id}: identifying {it!r} failed")
        raise _fail_request(request_logger, request_id, exc) from exc

    _record_identification(result)
    return _prepare_media_info_response(request_logger, result.media, request_id, result)


@app.get("/api/media-info")
@logger.trace("/api/media-info")
def get_media_info(
    request: Request,
    request_logger: RequestLoggerDep,
    identifier: MediaIdentifierDep,
    media_type: Annotated[str | None, Query(description="Type of media (movie, series, episode)")] = None,
    year: Annotated[int | None, Query(description="Release year of the media")] = None,
    title: Annotated[str | None, Query(description="Title of the media", max_length=MAX_INPUT_LENGTH)] = None,
    season: Annotated[
        int | None, Query(description="Season number of the media (0 for specials)", ge=0, le=MAX_SEASON_OR_EPISODE)
    ] = None,
    episode: Annotated[
        int | None, Query(description="Episode number of the media", ge=1, le=MAX_SEASON_OR_EPISODE)
    ] = None,
) -> Response:
    """Return the media record for known metadata, skipping file name identification.

    ``media_type``, ``year`` and ``title`` are required, plus ``season`` and ``episode`` for TV. Returns 200 with
    the record, 204 when nothing matched, 400 on missing or invalid parameters, 422 on out-of-range numbers, 503
    (generic message) when TMDB is unavailable, and 500 (generic message) when the lookup fails otherwise.
    """
    client_ip = _client_ip(request)
    span = trace.get_current_span()
    if span.is_recording():
        span.set_attributes(
            {
                "http.method": request.method,
                "http.client_ip": client_ip,
                "media.type": media_type,
                "media.title": title,
                "media.year": year,
            }
        )
        if season:
            span.set_attribute("media.season", season)
        if episode:
            span.set_attribute("media.episode", episode)

    if not media_type or not year or not title:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Required information is missing. You must provide media_type, year, and title.",
        )

    normalized_media_type = normalize_media_type(media_type)

    if normalized_media_type is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid media_type. Supported types are 'movie' and 'tv'."
        )

    if is_tv(normalized_media_type):
        if season is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Season number is required for TV shows."
            )

        if episode is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Episode number is required for TV shows."
            )

    current_year = datetime.now(UTC).year
    if year < FIRST_ACCEPTED_YEAR or year > current_year:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Year must be between {FIRST_ACCEPTED_YEAR} and the current year ({current_year}).",
        )

    requested = {
        "media_type": normalized_media_type,
        "title": title,
        "year": year,
        "season": season,
        "episode": episode,
    }
    request_id = request_logger.log_start(
        "/api/media-info", urlencode({key: value for key, value in requested.items() if value is not None}), client_ip
    )
    set_request_id(request_id)

    try:
        result = identifier.get_media_info(
            media_type=normalized_media_type,
            year=year,
            title=title,
            season=season,
            episode=episode,
        )
    except UpstreamUnavailableError as exc:
        logger.warning(f"Request {request_id}: media info lookup needs an unavailable service ({exc.cause_label})")
        raise _fail_unavailable(request_logger, request_id, exc) from exc
    except Exception as exc:
        logger.exception(f"Request {request_id}: media info lookup failed")
        raise _fail_request(request_logger, request_id, exc) from exc

    _record_identification(result)
    return _prepare_media_info_response(request_logger, result.media, request_id, result)


@app.get("/api/media-info/{media_id}")
@logger.trace("/api/media-info/{media_id}")
def get_media_info_by_id(
    request: Request,
    media_id: UUID,
    request_logger: RequestLoggerDep,
    cache_repository: CacheRepositoryDep,
) -> Response:
    """Return a cached media record by its id: 200 with the record, 404 when unknown, 500 when the lookup fails."""
    client_ip = _client_ip(request)
    span = trace.get_current_span()
    if span.is_recording():
        span.set_attributes({"http.method": request.method, "http.client_ip": client_ip, "media.id": str(media_id)})

    request_id = request_logger.log_start("/api/media-info/{media_id}", str(media_id), client_ip)
    set_request_id(request_id)

    try:
        cached_media = cache_repository.get_cached_by_id(str(media_id))
    except Exception as exc:
        logger.exception(f"Request {request_id}: media lookup by id failed")
        raise _fail_request(request_logger, request_id, exc) from exc

    if cached_media is None:
        status_code = status.HTTP_404_NOT_FOUND
        error_detail = "Media not found"
        request_logger.log_completed(request_id, status_code, error_message=error_detail)
        raise HTTPException(status_code=status_code, detail=error_detail)

    return _prepare_media_info_response(request_logger, cached_media, request_id)


@app.get("/api/health")
async def health_check() -> JSONResponse:
    """Report that the API process is up."""
    return JSONResponse(content={"message": "healthy"}, status_code=status.HTTP_200_OK)


@app.get("/api/statistics", response_model=None)
@logger.trace("/api/statistics")
def get_statistics(
    request_logger: RequestLoggerDep,
    num_requests: Annotated[
        int, Query(description="Number of recent requests to return", ge=1, le=MAX_STATISTICS_REQUESTS)
    ] = 100,
) -> list[dict[str, Any]]:
    """Return the most recent requests, newest first, with status, result id, timing, error message, outcome and
    deciding step.

    A server error shows only the generic message, plus the exception class (500) or the service and reason (503).
    """
    try:
        return [_public_request_entry(entry) for entry in request_logger.get_recent_requests(num_requests)]
    except Exception as exc:
        logger.exception("Retrieving statistics failed")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=INTERNAL_ERROR_DETAIL) from exc


if __name__ == "__main__":
    # Flush ALL OTEL log handlers before starting uvicorn.
    # On Windows the BatchLogRecordProcessor's background HTTP export
    # can deadlock with ProactorEventLoop initialisation if both run
    # concurrently.  Every TracedLogger (API, RequestLogger, Cache, etc.)
    # has its own BatchLogRecordProcessor; we must drain them all.
    print("Flushing buffered OTEL log records before starting uvicorn.")
    flush_all_otel_loggers()

    print("Starting uvicorn server.")
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)

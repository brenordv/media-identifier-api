"""HTTP API: identify media from a file name or from known metadata, and report on past requests."""

from dotenv import load_dotenv

load_dotenv()

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from functools import cache
from pathlib import Path
from typing import Annotated, Any
from uuid import UUID

from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response, status
from fastapi.responses import JSONResponse
from opentelemetry import trace
from raccoontools_db import close_pool, create_pool

from src.database.migrations import apply_migrations
from src.database.pool import build_pool_config
from src.media_identifiers.media_identifier import MediaIdentifier
from src.media_identifiers.media_type_helpers import is_tv, normalize_media_type
from src.media_identifiers.pipeline.base import PipelineExecutionError
from src.models.media_info import MediaData
from src.repositories.media_info_cache import MediaInfoCache
from src.repositories.repository_factory import get_cache_repository, get_request_logger
from src.repositories.request_logger import RequestLogger
from src.utils import flush_all_otel_loggers, get_otel_log_handler, set_request_id

MAX_INPUT_LENGTH = 1024
MAX_STATISTICS_REQUESTS = 1000
FIRST_ACCEPTED_YEAR = 1900
INTERNAL_ERROR_DETAIL = "Internal error while processing the request."


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Apply pending database migrations, then open the connection pool; close the pool on shutdown."""
    pool_config = build_pool_config()
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
    version="1.0.0",
    lifespan=lifespan,
)

logger = get_otel_log_handler("API", fastapi_app=app)


@cache
def get_media_identifier() -> MediaIdentifier:
    """Return the shared media identifier."""
    return MediaIdentifier(get_cache_repository())


RequestLoggerDep = Annotated[RequestLogger, Depends(get_request_logger)]
CacheRepositoryDep = Annotated[MediaInfoCache, Depends(get_cache_repository)]
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


@logger.trace("_prepare_media_info_response")
def _prepare_media_info_response(
    request_logger: RequestLogger, media_data: MediaData | None, request_id: str
) -> Response:
    if not media_data:
        status_code = status.HTTP_204_NO_CONTENT
        request_logger.log_completed(request_id, status_code, None)
        return Response(status_code=status_code)

    status_code = status.HTTP_200_OK
    media_id = media_data.get("id")
    request_logger.log_completed(request_id, status_code, str(media_id) if media_id is not None else None)

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
def _process_guess_filename(identifier: MediaIdentifier, it: str, is_retrying: bool = False) -> MediaData | None:
    try:
        filename = _sanitize_filename(it)

        if is_retrying:
            return identifier.get_media_info_by_filename(Path(filename).name)

        return identifier.get_media_info_by_filename(filename)
    except PipelineExecutionError as e:
        if is_retrying:
            raise
        logger.warning(f"Pipeline failed for full path ({e}). Retrying with filename only for: {it!r}")
        return _process_guess_filename(identifier, it, True)


@app.get("/api/guess")
@logger.trace("/api/guess")
def guess_filename(
    request: Request,
    request_logger: RequestLoggerDep,
    identifier: MediaIdentifierDep,
    it: Annotated[str | None, Query(description="Filename to analyze", max_length=MAX_INPUT_LENGTH)] = None,
) -> Response:
    """Identify the media a file name refers to.

    Returns 200 with the media record, 204 when nothing could be identified, 400 when ``it`` is missing, and 500
    (generic message) when identification fails.
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
        media_data = _process_guess_filename(identifier, it)
    except Exception as exc:
        logger.exception(f"Request {request_id}: identifying {it!r} failed")
        raise _fail_request(request_logger, request_id, exc) from exc

    return _prepare_media_info_response(request_logger, media_data, request_id)


@app.get("/api/media-info")
@logger.trace("/api/media-info")
def get_media_info(
    request: Request,
    request_logger: RequestLoggerDep,
    identifier: MediaIdentifierDep,
    media_type: Annotated[str | None, Query(description="Type of media (movie, series, episode)")] = None,
    year: Annotated[int | None, Query(description="Release year of the media")] = None,
    title: Annotated[str | None, Query(description="Title of the media", max_length=MAX_INPUT_LENGTH)] = None,
    season: Annotated[int | None, Query(description="Season number of the media")] = None,
    episode: Annotated[int | None, Query(description="Episode number of the media")] = None,
) -> Response:
    """Return the media record for known metadata, skipping file name identification.

    ``media_type``, ``year`` and ``title`` are required, plus ``season`` and ``episode`` for TV. Returns 200 with
    the record, 204 when nothing matched, 400 on missing or invalid parameters, and 500 (generic message) when the
    lookup fails.
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
        if not season:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Season number is required for TV shows."
            )

        if not episode:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Episode number is required for TV shows."
            )

    current_year = datetime.now(UTC).year
    if year < FIRST_ACCEPTED_YEAR or year > current_year:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Year must be between {FIRST_ACCEPTED_YEAR} and the current year ({current_year}).",
        )

    request_id = request_logger.log_start("/api/media-info", request.url.query, client_ip)
    set_request_id(request_id)

    try:
        media_data = identifier.get_media_info(
            media_type=normalized_media_type,
            year=year,
            title=title,
            season=season,
            episode=episode,
        )
    except Exception as exc:
        logger.exception(f"Request {request_id}: media info lookup failed")
        raise _fail_request(request_logger, request_id, exc) from exc

    return _prepare_media_info_response(request_logger, media_data, request_id)


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
    """Return the most recent requests, newest first, with status, result id, timing and error message."""
    try:
        return request_logger.get_recent_requests(num_requests)
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

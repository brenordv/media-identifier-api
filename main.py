from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

from datetime import datetime, UTC
from uuid import UUID

import traceback
from fastapi import FastAPI, HTTPException, Query, Request, Response, status
from fastapi.responses import JSONResponse
from opentelemetry import trace

from src.media_identifiers.pipeline.base import PipelineExecutionError
from src.media_identifiers.media_type_helpers import is_tv, normalize_media_type
from src.utils import set_request_id, get_otel_log_handler, flush_all_otel_loggers
from src.media_identifiers.media_identifier import MediaIdentifier
from src.repositories.repository_factory import get_repository


app = FastAPI(
    title="GuessIt API",
    description="API for guessing information from filenames using guessit",
    version="1.0.0"
)

logger = get_otel_log_handler("API")
request_logger = get_repository('request_logger')
cache_repository = get_repository('cache')
media_info_extender = MediaIdentifier()


@logger.trace("_prepare_media_info_response")
def _prepare_media_info_response(media_data, request_id):
    if media_data is None or len(media_data) == 0:
        status_code = status.HTTP_204_NO_CONTENT
        request_logger.log_completed(request_id, status_code, None)
        return Response(status_code=status_code)

    status_code = status.HTTP_200_OK
    request_logger.log_completed(request_id, status_code, media_data.get('id') if media_data else None)

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
def _process_guess_filename(it: str, is_retrying: bool = False):
    try:
        filename = _sanitize_filename(it)

        if is_retrying:
            it_file = Path(filename).name
            return media_info_extender.get_media_info_by_filename(it_file)

        return media_info_extender.get_media_info_by_filename(filename)
    except PipelineExecutionError as e:
        if is_retrying:
            raise
        logger.warning(f"Pipeline failed for full path. Retrying with filename only for: {it}")
        return _process_guess_filename(it, True)

@app.get("/api/guess")
@logger.trace("/api/guess")
async def guess_filename(
        request: Request,
        it: str = Query(None, description="Filename to analyze")):
    span = trace.get_current_span()
    if span.is_recording():
        span.set_attributes({
            "http.method": request.method,
            "http.client_ip": request.client.host,
            "media.input_filename": it,
        })
    """
    Analyze a filename using guessit and return the extracted information.

    Args:
        request: The FastAPI request object
        it: The filename to analyze

    Returns:
        JSON object with the media information
        
    Raises:
        400: If the filename is not provided
        500: If there's an error during execution
    """
    # Check if the filename is provided
    if not it:
        raise HTTPException(status_code=400, detail="Filename not provided")
    
    # Get the client's IP address
    client_ip = request.client.host

    request_id = request_logger.log_start("/api/guess", it, client_ip)

    try:
        set_request_id(request_id)

        media_data = _process_guess_filename(it)

        return _prepare_media_info_response(media_data, request_id)
    except Exception as e:
        # Capture the error and return a 500 response
        error_detail = f"Error processing filename: {str(e)}"
        traceback.print_exc()  # Print traceback for debugging
        status_code = 500

        request_logger.log_completed(request_id, status_code, error_message=error_detail)
        
        raise HTTPException(status_code=status_code, detail=error_detail)


@app.get("/api/media-info")
@logger.trace("/api/media-info")
async def get_media_info(
        request: Request,
        media_type: str = Query(None, description="Type of media (movie, series, episode)"),
        year: int = Query(None, description="Release year of the media"),
        title: str = Query(None, description="Title of the media"),
        season: int = Query(None, description="Season number of the media"),
        episode: int = Query(None, description="Episode number of the media"),
):
    span = trace.get_current_span()
    if span.is_recording():
        span.set_attributes({
            "http.method": request.method,
            "http.client_ip": request.client.host,
            "media.type": media_type,
            "media.title": title,
            "media.year": year,
        })
        if season: span.set_attribute("media.season", season)
        if episode: span.set_attribute("media.episode", episode)
    """
    Similar to the `/api/media-info` endpoint and will return the same information but will skip the identification step.
    This endpoint assumes you know the media you want info about.

    Args:
        request: The FastAPI request object.
        media_type: Type of media. (Required one: movie, tv)
        year: Release year of the media. (Required)
        title: Title of the media. (Required)
        season: Season number of the media. (Required if media_type is tv)
        episode: Episode number of the media. (Required if media_type is tv)

    Returns:
        JSON object with the media information

    Raises:
        400: If required information is not provided.
        500: If there's an error during execution
    """
    # Check if required data is provided
    if not media_type or not year or not title:
        raise HTTPException(status_code=400, detail="Required information is missing. You must provide media_type, year, and title.")

    normalized_media_type = normalize_media_type(media_type)

    if normalized_media_type is None:
        raise HTTPException(status_code=400, detail="Invalid media_type. Supported types are 'movie' and 'tv'.")

    if is_tv(normalized_media_type):
        if not season:
            raise HTTPException(status_code=400, detail="Season number is required for TV shows.")

        if not episode:
            raise HTTPException(status_code=400, detail="Episode number is required for TV shows.")

    if not isinstance(year, int):
        raise HTTPException(status_code=400, detail="Year must be an integer.")

    current_year = datetime.now(UTC).year
    if year < 1900 or year > current_year:
        raise HTTPException(status_code=400, detail=f"Year must be between 1900 and the current year ({current_year}).")

    # Get the client's IP address
    client_ip = request.client.host

    request_id = request_logger.log_start("/api/media-info", request.url.query, client_ip)

    try:
        set_request_id(request_id)

        media_data = media_info_extender.get_media_info(
            media_type=normalized_media_type,
            year=year,
            title=title,
            season=season,
            episode=episode,
        )

        return _prepare_media_info_response(media_data, request_id)
    except Exception as e:
        # Capture the error and return a 500 response
        error_detail = f"Error getting media info: {str(e)}"
        traceback.print_exc()  # Print traceback for debugging
        status_code = 500

        request_logger.log_completed(request_id, status_code, error_message=error_detail)

        raise HTTPException(status_code=status_code, detail=error_detail)


@app.get("/api/media-info/{media_id}")
@logger.trace("/api/media-info/{media_id}")
async def get_media_info_by_id(
        request: Request,
        media_id: UUID,
):
    span = trace.get_current_span()
    if span.is_recording():
        span.set_attributes({
            "http.method": request.method,
            "http.client_ip": request.client.host,
            "media.id": str(media_id),
        })
    """
    Retrieve media information directly from the cache using the media ID.

    Args:
        request: The FastAPI request object.
        media_id: Unique identifier of the media in the cache.

    Returns:
        JSON object with the media information if found.

    Raises:
        404: If the media is not found in the cache.
        500: If there's an error during execution.
    """
    client_ip = request.client.host
    request_id = request_logger.log_start("/api/media-info/{media_id}", str(media_id), client_ip)

    try:
        set_request_id(request_id)
        cached_media = cache_repository.get_cached(str(media_id), None, "id")
    except Exception as exc:
        error_detail = f"Error retrieving media by id: {str(exc)}"
        traceback.print_exc()
        status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
        request_logger.log_completed(request_id, status_code, error_message=error_detail)
        raise HTTPException(status_code=status_code, detail=error_detail)

    if cached_media is None:
        status_code = status.HTTP_404_NOT_FOUND
        error_detail = "Media not found"
        request_logger.log_completed(request_id, status_code, error_message=error_detail)
        raise HTTPException(status_code=status_code, detail=error_detail)

    return _prepare_media_info_response(cached_media, request_id)


@app.get("/api/health")
#@logger.trace("/api/health")
async def health_check():
    """
    Health check endpoint that verifies guessit is working correctly.
    
    Tests two specific filenames and checks if guessit correctly identifies them.
    
    Returns:
        200 with a "healthy" message if both tests pass
        400 with a "broken" message if any test fails
    """
    try:
        return JSONResponse(content={"message": "healthy"}, status_code=200)
    except Exception as e:
        # If any error occurs, return a broken status
        error_detail = f"Health check failed: {str(e)}"
        traceback.print_exc()  # Print traceback for debugging
        return JSONResponse(content={"message": "broken", "error": error_detail}, status_code=500)


@app.get("/api/statistics")
@logger.trace("/api/statistics")
async def get_statistics(num_requests: int = Query(100, description="Number of recent requests to return")):
    """
    Get statistics about the requests made to the /api/guess endpoint.
    
    Args:
        num_requests: Number of recent requests to return. Defaults to 100.
        
    Returns:
        JSON object with statistics about the requests:
        - total: Total number of requests ever made to the API
        - total_24h: Total number of requests in the past 24 hours
        - recent_requests: List of the most recent N requests
    """
    try:
        stats = request_logger.get_recent_requests(num_requests)
        return stats
    except Exception as e:
        error_detail = f"Error retrieving statistics: {str(e)}"
        traceback.print_exc()  # Print traceback for debugging
        raise HTTPException(status_code=500, detail=error_detail)


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

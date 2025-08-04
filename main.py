from dotenv import load_dotenv

from src.utils import set_request_id

load_dotenv()

import traceback
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse

from src.media_identifiers.media_identifier import MediaIdentifier
from src.repositories.repository_factory import get_repository


app = FastAPI(
    title="GuessIt API",
    description="API for guessing information from filenames using guessit",
    version="1.0.0"
)

request_logger = get_repository('request_logger')
media_info_extender = MediaIdentifier()


@app.get("/api/guess")
async def guess_filename(
        request: Request,
        it: str = Query(None, description="Filename to analyze")):
    """
    Analyze a filename using guessit and return the extracted information.
    
    Args:
        request: The FastAPI request object
        it: The filename to analyze
        
    Returns:
        JSON object with the guessit analysis result
        
    Raises:
        400: If the filename is not provided
        500: If there's an error during execution
    """
    # Check if the filename is provided
    if not it:
        raise HTTPException(status_code=400, detail="Filename not provided")
    
    # Get the client's IP address
    client_ip = request.client.host

    request_id = request_logger.log_start(it, client_ip)

    try:
        set_request_id(request_id)

        media_data = media_info_extender.identify_media(it)

        status_code = 200 if media_data or len(media_data) == 0 else 204

        request_logger.log_completed(request_id, status_code, media_data.get('id') if media_data else None)

        # Convert result to a serializable format
        serializable_result = {k: str(v) if not isinstance(v, (str, int, float, bool, list, dict, type(None))) else v 
                              for k, v in media_data.items()}

        return JSONResponse(content=serializable_result, status_code=status_code)
    except Exception as e:
        # Capture the error and return a 500 response
        error_detail = f"Error processing filename: {str(e)}"
        traceback.print_exc()  # Print traceback for debugging
        status_code = 500

        request_logger.log_completed(request_id, status_code, error_message=error_detail)
        
        raise HTTPException(status_code=status_code, detail=error_detail)

@app.get("/api/health")
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
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
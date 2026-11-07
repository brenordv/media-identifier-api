"""Process-wide repository instances.

Repositories do no I/O when they are built; they borrow connections from the process-wide pool, which must be
created (``raccoontools_db.create_pool``) before the first query.
"""

from functools import cache

from src.repositories.media_info_cache import MediaInfoCache
from src.repositories.openai_logger import OpenAILogger
from src.repositories.request_logger import RequestLogger


@cache
def get_cache_repository() -> MediaInfoCache:
    """Return the shared media cache repository."""
    return MediaInfoCache()


@cache
def get_request_logger() -> RequestLogger:
    """Return the shared request history repository."""
    return RequestLogger()


@cache
def get_openai_logger() -> OpenAILogger:
    """Return the shared OpenAI token usage repository."""
    return OpenAILogger()

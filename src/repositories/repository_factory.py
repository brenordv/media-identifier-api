import os
from psycopg2.pool import SimpleConnectionPool

from src.repositories.openai_logger import OpenAILogger
from src.repositories.request_logger import RequestLogger
from src.repositories.media_info_cache import MediaInfoCache

_db_pool = SimpleConnectionPool(
    minconn = 1,
    maxconn = 10,
    host = os.environ.get('POSTGRES_HOST', 'localhost'),
    port = os.environ.get('POSTGRES_PORT', '5432'),
    user = os.environ.get('POSTGRES_USER', 'postgres'),
    password=os.environ.get('POSTGRES_PASSWORD', 'postgres'),
    dbname = 'extended_media_info'
)

def get_repository(repo_name):
    repo_name = repo_name.lower()

    if repo_name == 'cache':
        return MediaInfoCache(_db_pool)

    if repo_name == 'request_logger':
        return RequestLogger(_db_pool)

    if repo_name == 'openai_logger':
        return OpenAILogger(_db_pool)

    raise ValueError(f"Repository '{repo_name}' is not recognized or not implemented.")
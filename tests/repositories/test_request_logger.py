from datetime import datetime, timedelta
from uuid import UUID

from psycopg.rows import dict_row

from src.repositories.request_logger import RequestLogger
from tests.fakes import FakePool

REQUEST_ID = UUID("2577e39f-6ca8-4450-adae-f6395efc4862")
MEDIA_ID = UUID("ed6822d6-e603-4dc9-8556-1a5289a950a7")


def test_log_start_returns_the_new_request_id_as_text() -> None:
    pool = FakePool(rows=[(REQUEST_ID,)])
    request_logger = RequestLogger(pool_getter=pool.getter())

    request_id = request_logger.log_start("/api/guess", "Fargo.1996.mkv", "127.0.0.1")

    assert request_id == str(REQUEST_ID)
    assert pool.cursor.executed[0][1] == ("/api/guess", "Fargo.1996.mkv", "127.0.0.1")
    assert pool.cursor.row_factories == [None]


def test_get_recent_requests_returns_ids_as_text() -> None:
    received_at = datetime.now()
    row = {
        "id": REQUEST_ID,
        "filename": "Fargo.1996.mkv",
        "requester_ip": "127.0.0.1",
        "result_status": 200,
        "result_media_id": MEDIA_ID,
        "received_at": received_at,
        "responded_at": received_at + timedelta(seconds=1),
        "elapsed_time": timedelta(seconds=1),
        "error_message": None,
    }
    pool = FakePool(rows=[row])
    request_logger = RequestLogger(pool_getter=pool.getter())

    requests = request_logger.get_recent_requests(5)

    assert requests[0]["id"] == str(REQUEST_ID)
    assert requests[0]["result_media_id"] == str(MEDIA_ID)
    assert pool.cursor.executed[0][1] == (5,)
    assert pool.cursor.row_factories == [dict_row]

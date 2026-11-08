from uuid import UUID

from src.repositories.openai_logger import OpenAILogger
from src.utils import set_request_id
from tests.fakes import FakePool

LOG_ID = UUID("6166a98e-8b98-4142-8105-ea6704ebb3d6")


def test_log_records_tokens_against_the_current_request() -> None:
    pool = FakePool(rows=[(LOG_ID,)])
    set_request_id("2577e39f-6ca8-4450-adae-f6395efc4862")

    log_id = OpenAILogger(pool.getter()).log(120, 20, 8, 3, 128)

    assert log_id == str(LOG_ID)
    assert pool.cursor.executed[0][1] == (120, 20, 8, 3, 128, "2577e39f-6ca8-4450-adae-f6395efc4862")
    assert pool.cursor.row_factories == [None]

from datetime import datetime

import pytest

from src.utils import FIRST_FILM_YEAR, get_request_id, is_valid_year, set_request_id


@pytest.mark.parametrize(
    ("year", "expected"),
    [
        (None, False),
        (195, False),
        (FIRST_FILM_YEAR - 1, False),
        (FIRST_FILM_YEAR, True),
        (datetime.now().year, True),
        (datetime.now().year + 1, False),
    ],
)
def test_is_valid_year_accepts_first_film_year_through_current_year(year: int | None, expected: bool) -> None:
    assert is_valid_year(year) is expected


def test_get_request_id_returns_the_id_set_in_this_context() -> None:
    set_request_id("request-42")

    assert get_request_id() == "request-42"

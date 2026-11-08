import traceback

import pytest

from src.database.pool import CONNECTION_STRING_SECRET, POOL_MAX_SIZE, build_conninfo, build_pool_config
from src.secret_store import SecretsError

FAKE_PASSWORD = "Fake-Pa55"
URI = f"postgresql://media:{FAKE_PASSWORD}@db.example:5433/media_cache"


@pytest.mark.parametrize(
    "conninfo",
    [
        URI,
        "postgresql://media:Fake%40Pa55%2F1@db.example:5433,db2.example:5433/media_cache?sslmode=require",
        f"host=db.example port=5433 user=media password='{FAKE_PASSWORD} two' dbname=media_cache",
        "host=/var/run/postgresql user=media dbname=media_cache",
    ],
)
def test_build_conninfo_returns_the_connection_string_as_stored(secret_values: dict[str, str], conninfo: str) -> None:
    secret_values[CONNECTION_STRING_SECRET] = conninfo

    assert build_conninfo() == conninfo


def test_build_conninfo_strips_surrounding_whitespace(secret_values: dict[str, str]) -> None:
    secret_values[CONNECTION_STRING_SECRET] = f" {URI}\n"

    assert build_conninfo() == URI


def test_build_conninfo_missing_secret_raises_naming_it() -> None:
    with pytest.raises(SecretsError, match=CONNECTION_STRING_SECRET):
        build_conninfo()


@pytest.mark.parametrize(
    "conninfo",
    [
        "postgresql://media:Fake%zzPa55@db.example:5433/media_cache",
        f"host=db.example user=media password={FAKE_PASSWORD} two dbname=media_cache",
        "postgresql://media:Fake@Pa55@db.example:5433/media_cache",
        "postgresql://media:Fake/Pa55@db.example:5433/media_cache",
        "postgresql://media:5432/Fake-Pa55@db.example:5433/media_cache",
        "postgresql://media:Fake/Pa55?sslmode=require@db.example:5433/media_cache",
        "postgresql://media@corp:Fake-Pa55@db.example:5433/media_cache",
        f"postgresql://media:{FAKE_PASSWORD}@db.example:5433",
        f"postgresql://media:{FAKE_PASSWORD}@db.example:5433/",
        f"host=db.example user=media password={FAKE_PASSWORD} dbname=''",
    ],
)
def test_build_conninfo_invalid_string_raises_without_revealing_the_password(
    secret_values: dict[str, str], conninfo: str
) -> None:
    secret_values[CONNECTION_STRING_SECRET] = conninfo

    with pytest.raises(ValueError, match=CONNECTION_STRING_SECRET) as raised:
        build_conninfo()

    assert raised.value.__cause__ is None
    assert raised.value.__context__ is None
    rendered = "".join(traceback.format_exception(raised.value))
    assert all(fragment not in rendered for fragment in ("Fake", "Pa55", "two"))


def test_build_pool_config_keeps_the_password_out_of_repr(secret_values: dict[str, str]) -> None:
    secret_values[CONNECTION_STRING_SECRET] = URI

    config = build_pool_config()

    assert config.max_size == POOL_MAX_SIZE
    assert FAKE_PASSWORD not in repr(config)

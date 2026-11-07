import pytest
from psycopg.conninfo import conninfo_to_dict

from src.database.pool import DEFAULT_DATABASE_NAME, POOL_MAX_SIZE, build_conninfo, build_pool_config


@pytest.fixture
def database_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("POSTGRES_HOST", "db.example")
    monkeypatch.setenv("POSTGRES_PORT", "5433")
    monkeypatch.setenv("POSTGRES_USER", "media")
    monkeypatch.setenv("POSTGRES_PASSWORD", "s3cret")


@pytest.mark.usefixtures("database_env")
def test_build_conninfo_uses_the_postgres_variables_and_default_database() -> None:
    settings = conninfo_to_dict(build_conninfo())

    assert settings == {
        "host": "db.example",
        "port": "5433",
        "user": "media",
        "password": "s3cret",
        "dbname": DEFAULT_DATABASE_NAME,
    }


@pytest.mark.usefixtures("database_env")
def test_build_conninfo_honors_postgres_db(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("POSTGRES_DB", "media_cache")

    assert conninfo_to_dict(build_conninfo())["dbname"] == "media_cache"


@pytest.mark.usefixtures("database_env")
@pytest.mark.parametrize("missing", ["POSTGRES_HOST", "POSTGRES_PORT", "POSTGRES_USER", "POSTGRES_PASSWORD"])
def test_build_conninfo_missing_variable_raises_naming_it(monkeypatch: pytest.MonkeyPatch, missing: str) -> None:
    monkeypatch.delenv(missing)

    with pytest.raises(ValueError, match=missing):
        build_conninfo()


@pytest.mark.usefixtures("database_env")
def test_build_conninfo_non_numeric_port_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("POSTGRES_PORT", "fivefourthreetwo")

    with pytest.raises(ValueError, match="POSTGRES_PORT"):
        build_conninfo()


@pytest.mark.usefixtures("database_env")
def test_build_pool_config_keeps_the_password_out_of_repr() -> None:
    config = build_pool_config()

    assert config.max_size == POOL_MAX_SIZE
    assert "s3cret" not in repr(config)

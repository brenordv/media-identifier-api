import logging
from pathlib import Path

import pytest

from src.database import migrate
from src.database.migrations import Migration

SECRET_PASSWORD = "Sup3r-S3cret-Password"


def test_main_without_database_settings_exits_1_naming_the_variable(capsys: pytest.CaptureFixture[str]) -> None:
    assert migrate.main() == 1

    assert "POSTGRES_PORT" in capsys.readouterr().err


def test_main_connection_failure_exits_1_without_revealing_the_password(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setenv("POSTGRES_HOST", "127.0.0.1")
    monkeypatch.setenv("POSTGRES_PORT", "1")
    monkeypatch.setenv("POSTGRES_USER", "media")
    monkeypatch.setenv("POSTGRES_PASSWORD", SECRET_PASSWORD)
    monkeypatch.setenv("PGCONNECT_TIMEOUT", "2")

    with caplog.at_level(logging.DEBUG):
        exit_code = migrate.main()

    output = capsys.readouterr()
    assert exit_code == 1
    assert "Migration failed" in output.err
    assert SECRET_PASSWORD not in output.out + output.err
    assert all(SECRET_PASSWORD not in record.getMessage() for record in caplog.records)


def test_main_reports_the_applied_migrations(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    applied = [Migration(2, "cache_identity_per_media_type", "SELECT 1;", "checksum")]
    monkeypatch.setattr(migrate, "build_conninfo", lambda: "host=db.example")
    monkeypatch.setattr(migrate, "apply_migrations", lambda conninfo, logger: applied)

    assert migrate.main() == 0

    assert "0002_cache_identity_per_media_type" in capsys.readouterr().out


def test_main_with_current_schema_says_so(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setattr(migrate, "build_conninfo", lambda: "host=db.example")
    monkeypatch.setattr(migrate, "apply_migrations", lambda conninfo, logger: [])

    assert migrate.main() == 0

    assert "up to date" in capsys.readouterr().out


def test_migrations_folder_ships_with_the_application() -> None:
    dockerignore = (Path(__file__).resolve().parents[2] / ".dockerignore").read_text(encoding="utf-8")

    assert "!migrations/" in dockerignore.splitlines()

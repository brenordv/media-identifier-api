"""Test-session setup: the suite runs without live services unless the integration run is explicitly requested."""

import os
from collections.abc import Iterator

import pytest

INTEGRATION_FLAG = "MEDIA_IDENTIFIER_RUN_INTEGRATION"
_LIVE_SETTINGS = (
    "POSTGRES_HOST",
    "POSTGRES_PORT",
    "POSTGRES_USER",
    "POSTGRES_PASSWORD",
    "POSTGRES_DB",
    "TMDB_API_KEY",
    "OPENAI_API_KEY",
    "OPENAI_ORGANIZATION",
    "OPENAI_MODEL",
    "NIMBLE_URL",
)


def _integration_requested(config: pytest.Config) -> bool:
    return os.environ.get(INTEGRATION_FLAG) == "1" and config.getoption("markexpr") == "integration"


def pytest_configure(config: pytest.Config) -> None:
    """Keep `.env` unloaded, telemetry off and live credentials out of the environment for unit runs.

    Runs before any test module (and so any ``src`` or ``main`` import) is collected.
    """
    if _integration_requested(config):
        return

    os.environ["PYTHON_DOTENV_DISABLED"] = "1"
    os.environ["OTEL_SDK_DISABLED"] = "true"
    os.environ["OTEL_EXPORTER_OTLP_ENDPOINT"] = "http://127.0.0.1:4318"
    for name in _LIVE_SETTINGS:
        os.environ.pop(name, None)


@pytest.fixture(autouse=True)
def _clear_request_id() -> Iterator[None]:
    """Keep the request id one test sets from leaking into the next test on the same thread."""
    yield

    from src.utils import set_request_id

    set_request_id(None)

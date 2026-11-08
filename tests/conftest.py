"""Test-session setup: the suite runs without live services unless the integration run is explicitly requested."""

import os
from collections.abc import Iterator

import pytest

INTEGRATION_FLAG = "MEDIA_IDENTIFIER_RUN_INTEGRATION"


def _integration_requested(config: pytest.Config) -> bool:
    return os.environ.get(INTEGRATION_FLAG) == "1" and config.getoption("markexpr") == "integration"


def pytest_configure(config: pytest.Config) -> None:
    """Keep `.env` unloaded, telemetry off and the Infisical bootstrap out of the environment for unit runs.

    Runs before any test module (and so any ``src`` or ``main`` import) is collected.
    """
    if _integration_requested(config):
        return

    os.environ["PYTHON_DOTENV_DISABLED"] = "1"
    os.environ["OTEL_SDK_DISABLED"] = "true"
    os.environ["OTEL_EXPORTER_OTLP_ENDPOINT"] = "http://127.0.0.1:4318"

    from src.secret_store import REQUIRED_BOOTSTRAP_VARIABLES

    for name in (*REQUIRED_BOOTSTRAP_VARIABLES, "INFISICAL_ENV", "OPENAI_MODEL"):
        os.environ.pop(name, None)


@pytest.fixture(autouse=True)
def secret_values(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
    """Serve the Infisical secrets from a dict that starts empty, so every setting is absent unless a test sets it.

    Integration tests read the real Infisical instead. The store caches what it reads, so a test fills the dict before
    the code under test reads the secret.
    """
    values: dict[str, str] = {}
    if request.node.get_closest_marker("integration") is None:
        from src import secret_store

        monkeypatch.setattr(secret_store, "_default_store", secret_store.SecretStore(values.get, "test secrets"))
    return values


@pytest.fixture(autouse=True)
def _clear_request_id() -> Iterator[None]:
    """Keep the request id one test sets from leaking into the next test on the same thread."""
    yield

    from src.utils import set_request_id

    set_request_id(None)

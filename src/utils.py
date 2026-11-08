"""Shared helpers: the request-scoped id, year validation, and the OpenTelemetry-backed logger factory."""

import contextvars
import os
from datetime import datetime

from fastapi import FastAPI
from simple_log_factory_ext_otel import TracedLogger, otel_log_factory

SERVICE_NAME = "media-identifier-api"
FIRST_FILM_YEAR = 1888
UNTRACED_URLS = "api/health"

request_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar("request_id", default=None)
_all_loggers: dict[int, TracedLogger] = {}


def set_request_id(request_id: str | None) -> None:
    """Store the id of the request being handled in the current context.

    Args:
        request_id: The ``request_history`` id of the request, or None to clear it.
    """
    request_id_var.set(request_id)


def get_request_id() -> str | None:
    """Return the request id stored in the current context.

    Returns:
        The id set by :func:`set_request_id`, or None when no request is being handled.
    """
    return request_id_var.get()


def is_valid_year(year: int | None) -> bool:
    """Tell whether a year can be the release year of a film or show.

    Args:
        year: The year to check.

    Returns:
        True when the year lies between the first film ever made (1888) and the current year.
    """
    if year is None:
        return False

    return FIRST_FILM_YEAR <= year <= datetime.now().year


def get_otel_log_handler(log_name: str, fastapi_app: FastAPI | None = None) -> TracedLogger:
    """Create (or reuse) a logger that exports logs and traces to the OTLP endpoint.

    Every logger also instruments psycopg, so database calls show up as spans. When ``fastapi_app`` is given,
    the app is instrumented too, except for the health check.

    Args:
        log_name: Name of the logger.
        fastapi_app: The application to instrument, if any.

    Returns:
        The traced logger.

    Raises:
        ValueError: If ``OTEL_EXPORTER_OTLP_ENDPOINT`` is not set.
    """
    otel_endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT")

    if not otel_endpoint:
        raise ValueError("OTEL_EXPORTER_OTLP_ENDPOINT environment variable must be set.")

    traced = otel_log_factory(
        service_name=SERVICE_NAME,
        log_name=log_name,
        otel_exporter_endpoint=otel_endpoint,
        instrument_db={"psycopg": {"enable_commenter": True}},
        instrument_fastapi=({"app": fastapi_app, "excluded_urls": UNTRACED_URLS} if fastapi_app is not None else None),
    )

    _all_loggers[id(traced)] = traced

    return traced


def flush_all_otel_loggers() -> None:
    """Flush every OtelLogHandler created via get_otel_log_handler().

    Must be called before uvicorn.run() on Windows to drain all
    BatchLogRecordProcessor queues and avoid a deadlock between
    the batch-export background threads and ProactorEventLoop init.
    """
    for traced in _all_loggers.values():
        for h in traced.logger.handlers:
            h.flush()

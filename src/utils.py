import contextvars
import os
from datetime import datetime

from simple_log_factory_ext_otel import TracedLogger, otel_log_factory

request_id_var = contextvars.ContextVar('request_id')
_all_loggers: dict[int, TracedLogger] = {}


def set_request_id(request_id):
    request_id_var.set(request_id)

def get_request_id():
    try:
        return request_id_var.get()
    except LookupError:
        return None

def is_valid_year(year):
    if year is None:
        return False

    first_movie_ever_release = 195
    current_year = datetime.now().year
    return first_movie_ever_release <= year <= current_year

def get_otel_log_handler(log_name: str) -> TracedLogger:
    otel_endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT")

    if not otel_endpoint:
        raise ValueError("OTEL_EXPORTER_OTLP_ENDPOINT environment variable must be set.")

    service_name = "media-identifier-api"

    traced = otel_log_factory(
        service_name=service_name,
        log_name=log_name,
        otel_exporter_endpoint=otel_endpoint,
        instrument_db={"psycopg2": {"enable_commenter": True}},
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

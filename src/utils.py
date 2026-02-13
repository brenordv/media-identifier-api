import contextvars
import os
from datetime import datetime

from simple_log_factory.log_factory import log_factory
from simple_log_factory_ext_otel import (
    OtelLogHandler,
    OtelTracer,
    TracedLogger,
    create_resource,
)
from opentelemetry import trace

request_id_var = contextvars.ContextVar('request_id')
_otel_logger: TracedLogger | None = None

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
    global _otel_logger

    if _otel_logger is not None:
        return _otel_logger

    otel_endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT")

    if not otel_endpoint:
        raise ValueError("OTEL_EXPORTER_OTLP_ENDPOINT environment variable must be set.")

    service_name = "media-identifier-api"
    resource = create_resource(service_name)

    log_handler = OtelLogHandler(
        service_name=service_name,
        endpoint=f"{otel_endpoint}/v1/logs",
        protocol="http",
        resource=resource,
    )

    otel_tracer = OtelTracer(
        service_name=service_name,
        endpoint=f"{otel_endpoint}/v1/traces",
        protocol="http",
        resource=resource,
    )

    trace.set_tracer_provider(otel_tracer.provider)

    logger = log_factory(log_name=log_name, custom_handlers=[log_handler])

    _otel_logger = TracedLogger(logger=logger, tracer=otel_tracer.tracer)

    return _otel_logger

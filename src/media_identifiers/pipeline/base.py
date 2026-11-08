"""Core types of the identification pipeline: the shared context, step results, handlers and the controller."""

from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Literal, Self

from opentelemetry import trace
from simple_log_factory_ext_otel import TracedLogger

from src.media_identifiers.errors import UpstreamUnavailableError
from src.media_identifiers.nimble_classifier import NimbleVerdict
from src.models.media_identification_request import MediaIdentificationRequest, RequestMode
from src.models.media_info import MediaData, is_media_type_valid, merge_media_info
from src.repositories.media_info_cache import MediaInfoCache
from src.utils import get_otel_log_handler

_logger = get_otel_log_handler("Pipeline")


class StepStatus(StrEnum):
    """Outcome of one handler: continue (SUCCESS/SKIP) or stop with the run's answer (DONE)."""

    SUCCESS = "success"
    SKIP = "skip"
    DONE = "done"


class IdentificationOutcome(StrEnum):
    """The verdict of an identification run."""

    IDENTIFIED = "identified"
    """A cache hit, or TMDB matched a movie or a series."""
    NOT_MEDIA = "not_media"
    """The file is not a movie or TV release."""
    UNIDENTIFIED = "unidentified"
    """Every applicable step ran and none produced a TMDB match."""


DecidedBy = Literal["guessit", "nimble", "openai", "request"]
"""The step that settled the media type (or the not_media verdict); ``request`` when the caller supplied it."""


@dataclass
class StepResult:
    """What a handler reports back to the controller."""

    status: StepStatus
    message: str | None = None

    @classmethod
    def success(cls, message: str | None = None) -> Self:
        """The step changed the context; continue."""
        return cls(status=StepStatus.SUCCESS, message=message)

    @classmethod
    def skip(cls, message: str | None = None) -> Self:
        """The step had nothing to do; continue."""
        return cls(status=StepStatus.SKIP, message=message)

    @classmethod
    def done(cls, message: str | None = None) -> Self:
        """The pipeline has its answer; stop."""
        return cls(status=StepStatus.DONE, message=message)


@dataclass
class PipelineResult:
    """Final state of a pipeline run.

    Attributes:
        media: The media identified so far.
        cached: The cache hit that ended the run early, if any.
        completed: Whether a handler ended the run.
        outcome: A verdict a handler reached (``not_media``), or None when no handler reached one.
        decided_by: The step that settled the media type or the ``not_media`` verdict, if any.
    """

    media: MediaData | None
    cached: MediaData | None
    completed: bool
    outcome: IdentificationOutcome | None = None
    decided_by: DecidedBy | None = None


class PipelineExecutionError(RuntimeError):
    """A handler raised an unexpected error."""


class PipelineContext:
    """State shared by the handlers of one identification run.

    Args:
        request: The identification request.
        cache_repository: Cache used by the lookup steps.
        logger: Logger for the handlers; defaults to the pipeline logger.
    """

    def __init__(
        self,
        request: MediaIdentificationRequest,
        cache_repository: MediaInfoCache,
        logger: TracedLogger | None = None,
    ) -> None:
        self.request = request
        self.cache_repository = cache_repository
        self.logger = logger or _logger
        self.file_path = request.file_path
        self.media: MediaData | None = request.seed_media_info()
        self.cached_result: MediaData | None = None
        self.completed: bool = False
        self.errors: list[BaseException] = []
        self.outcome: IdentificationOutcome | None = None
        self.decided_by: DecidedBy | None = "request" if request.mode == RequestMode.METADATA else None
        self.guessit_reading: dict[str, Any] | None = None
        self.nimble_verdict: NimbleVerdict | None = None
        self.type_uncertain: bool = False
        self.openai_consulted: bool = False
        self.title_from_openai: bool = False
        self.deferred_upstream_error: UpstreamUnavailableError | None = None
        """An OpenAI outage the run continued without."""
        self.tmdb_searches: set[tuple[str, str | None, int | None]] = set()
        self.tmdb_no_match: bool = False
        self.step_readings: dict[str, str] = {}
        """What each step concluded, keyed by step name."""

    @property
    def mode(self) -> RequestMode:
        """The request mode."""
        return self.request.mode

    @property
    def media_type(self) -> str | None:
        """The media type identified so far, if any."""
        if self.media is None:
            return None
        media_type: str | None = self.media.get("media_type")
        return media_type

    @property
    def has_media_type(self) -> bool:
        """True once the media type is known to be ``movie`` or ``tv``."""
        return is_media_type_valid(self.media_type) if self.media_type else False

    @_logger.trace("PipelineContext.update_media")
    def update_media(self, new_media: MediaData | None) -> None:
        """Merge new values into the media identified so far (see ``merge_media_info``)."""
        if new_media is None:
            return
        self.media = merge_media_info(self.media, new_media)

    def mark_cached_result(self, cached: MediaData) -> None:
        """Store a cache hit and mark the run complete."""
        self.cached_result = cached
        self.completed = True

    def mark_not_media(self, decided_by: DecidedBy) -> None:
        """Record that the file is not a movie or TV release and mark the run complete."""
        self.outcome = IdentificationOutcome.NOT_MEDIA
        self.decided_by = decided_by
        self.completed = True

    def record_error(self, error: BaseException) -> None:
        """Keep an error raised by a handler."""
        self.errors.append(error)

    def finalize(self) -> PipelineResult:
        """Return the run's result."""
        return PipelineResult(
            media=self.media,
            cached=self.cached_result,
            completed=self.completed,
            outcome=self.outcome,
            decided_by=self.decided_by,
        )


class PipelineHandler:
    """One identification step. Subclasses decide in :meth:`handles` whether they apply, then :meth:`invoke`."""

    name: str = "pipeline_handler"

    def handles(self, context: PipelineContext) -> bool:
        """Tell whether the step applies to the current context."""
        return True

    def invoke(self, context: PipelineContext) -> StepResult:  # pragma: no cover - interface
        """Run the step."""
        raise NotImplementedError


class PipelineController:
    """Runs handlers in order until one finishes the run.

    Args:
        handlers: The steps, in order.
        logger: Logger for handler failures; defaults to the pipeline logger.
    """

    def __init__(self, handlers: Sequence[PipelineHandler], logger: TracedLogger | None = None) -> None:
        self.handlers = handlers
        self.logger = logger or _logger

    @_logger.trace("PipelineController.run")
    def run(self, context: PipelineContext) -> PipelineResult:
        """Run the pipeline.

        Returns:
            The result once a handler reports DONE or every handler ran.

        Raises:
            UpstreamUnavailableError: If a service a handler needs is unavailable (passed through unwrapped).
            PipelineExecutionError: If a handler raises any other error.
        """
        span = trace.get_current_span()
        if span.is_recording():
            span.set_attribute("pipeline.handler_count", len(self.handlers))

        for handler in self.handlers:
            if not handler.handles(context):
                continue
            handler_name = getattr(handler, "name", handler.__class__.__name__)
            try:
                result = handler.invoke(context)
            except UpstreamUnavailableError:
                raise
            except Exception as exc:
                context.record_error(exc)
                self.logger.error(f"[{handler_name}] raised unhandled error: {exc}")
                raise PipelineExecutionError(f"Handler '{handler_name}' execution failed: {exc}") from exc

            if result.status == StepStatus.DONE:
                context.completed = True
                return context.finalize()

        return context.finalize()

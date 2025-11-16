from dataclasses import dataclass
from enum import Enum
from typing import List, Optional, Sequence

from simple_log_factory.log_factory import log_factory

from src.models.media_identification_request import MediaIdentificationRequest, RequestMode
from src.models.media_info import is_media_type_valid, merge_media_info


class StepStatus(str, Enum):
    SUCCESS = "success"
    SKIP = "skip"
    DONE = "done"
    FATAL = "fatal"


@dataclass
class StepResult:
    status: StepStatus
    message: Optional[str] = None
    error: Optional[BaseException] = None

    @classmethod
    def success(cls, message: Optional[str] = None) -> "StepResult":
        return cls(status=StepStatus.SUCCESS, message=message)

    @classmethod
    def skip(cls, message: Optional[str] = None) -> "StepResult":
        return cls(status=StepStatus.SKIP, message=message)

    @classmethod
    def done(cls, message: Optional[str] = None) -> "StepResult":
        return cls(status=StepStatus.DONE, message=message)

    @classmethod
    def fatal(cls, message: Optional[str] = None, error: Optional[BaseException] = None) -> "StepResult":
        return cls(status=StepStatus.FATAL, message=message, error=error)


@dataclass
class PipelineResult:
    media: Optional[dict]
    cached: Optional[dict]
    completed: bool


class PipelineExecutionError(RuntimeError):
    pass


class PipelineContext:
    def __init__(
        self,
        request: MediaIdentificationRequest,
        cache_repository,
        logger=None,
    ):
        self.request = request
        self.cache_repository = cache_repository
        self.logger = logger or log_factory("Pipeline", unique_handler_types=True)
        self.file_path = request.file_path
        self.media: Optional[dict] = request.seed_media_info()
        self.cached_result: Optional[dict] = None
        self.completed: bool = False
        self.errors: List[BaseException] = []

    @property
    def mode(self) -> RequestMode:
        return self.request.mode

    @property
    def media_type(self) -> Optional[str]:
        if self.media is None:
            return None
        return self.media.get("media_type")

    @property
    def has_media_type(self) -> bool:
        return is_media_type_valid(self.media_type) if self.media_type else False

    def update_media(self, new_media: Optional[dict]) -> None:
        if new_media is None:
            return
        self.media = merge_media_info(self.media, new_media)

    def mark_cached_result(self, cached: dict) -> None:
        self.cached_result = cached
        self.completed = True

    def record_error(self, error: BaseException) -> None:
        self.errors.append(error)

    def finalize(self) -> PipelineResult:
        return PipelineResult(media=self.media, cached=self.cached_result, completed=self.completed)


class PipelineHandler:
    name: str = "pipeline_handler"

    def handles(self, context: PipelineContext) -> bool:
        return True

    def invoke(self, context: PipelineContext) -> StepResult:  # pragma: no cover - interface
        raise NotImplementedError


class PipelineController:
    def __init__(self, handlers: Sequence[PipelineHandler], logger=None):
        self.handlers = handlers
        self.logger = logger or log_factory("PipelineController", unique_handler_types=True)

    def run(self, context: PipelineContext) -> PipelineResult:
        for handler in self.handlers:
            if not handler.handles(context):
                continue
            handler_name = getattr(handler, "name", handler.__class__.__name__)
            try:
                result = handler.invoke(context)
            except Exception as exc:  # noqa: BLE001
                context.record_error(exc)
                self.logger.error(f"[{handler_name}] raised unhandled error: {exc}")
                raise PipelineExecutionError(
                    f"Handler '{handler_name}' execution failed: {exc}"
                ) from exc

            if result.status == StepStatus.SKIP:
                continue

            if result.status == StepStatus.SUCCESS:
                continue

            if result.status == StepStatus.DONE:
                context.completed = True
                return context.finalize()

            if result.status == StepStatus.FATAL:
                error = result.error or RuntimeError(result.message or "Pipeline handler failed.")
                context.record_error(error)
                raise PipelineExecutionError(result.message or "Pipeline handler failed.") from error

        return context.finalize()


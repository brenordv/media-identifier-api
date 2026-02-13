import inspect
import os
from typing import Optional, Union
from opentelemetry import trace
from openai import OpenAI, OpenAIError, RateLimitError

from src.media_identifiers.ai_functions import extract_movie_title_ai_function, extract_series_title_ai_function
from src.media_identifiers.ai_functions.extract_media_type_ai_function import extract_media_type_from_filename
from src.media_identifiers.ai_functions.extract_season_episode_ai_function import extract_season_episode_from_filename
from src.media_identifiers.helpers import apply_basic_media_attributes, parse_season_episode_string
from src.media_identifiers.media_type_helpers import (
    is_media_type_valid,
    is_movie,
)
from src.models.media_info import MediaInfoBuilder
from src.repositories.repository_factory import get_repository
from src.utils import get_otel_log_handler

_open_ai_model = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
_logger = get_otel_log_handler("MediaIdentifier")
_openai_request_logger = None
_open_ai_client = None


@_logger.trace("identify_media_with_open_ai_multi")
def identify_media_with_open_ai_multi(file_path: str, media_type: Union[str, None]) -> Optional[dict]:
    span = trace.get_current_span()
    if span.is_recording():
        span.set_attributes({
            "media.file_path": file_path,
            "media.type": media_type or "unknown",
        })

    if media_type is None:
        media_type = identify_media_type_with_open_ai(file_path)
        if not media_type:
            _logger.warning(f"Could not identify media type for file: {file_path}")
            return None
        if not is_media_type_valid(media_type):
            _logger.warning(f"Unknown media type: {media_type} for file: {file_path}")
            return None

    if is_movie(media_type):
        title = identify_movie_title_with_open_ai(file_path)
        season, episode = None, None
    else:
        title = identify_series_title_with_open_ai(file_path)
        season, episode = parse_season_episode_string(
            identify_series_season_episode_with_open_ai(file_path),
            logger=_logger,
        )

    builder = apply_basic_media_attributes(
        MediaInfoBuilder(),
        title=title,
        media_type=media_type,
        year=None,
        season=season,
        episode=episode,
        searchable_reference=title,
    )

    return builder \
        .with_used_openai(True) \
        .build()


@_logger.trace("identify_media_type_with_open_ai")
def identify_media_type_with_open_ai(file_path: str) -> Optional[str]:
    span = trace.get_current_span()
    if span.is_recording(): span.set_attribute("media.file_path", file_path)
    return _send_task_to_ai(file_path, extract_media_type_from_filename)


@_logger.trace("identify_movie_title_with_open_ai")
def identify_movie_title_with_open_ai(file_path: str) -> Optional[str]:
    span = trace.get_current_span()
    if span.is_recording(): span.set_attribute("media.file_path", file_path)
    return _send_task_to_ai(file_path, extract_movie_title_ai_function)


@_logger.trace("identify_series_title_with_open_ai")
def identify_series_title_with_open_ai(file_path: str) -> Optional[str]:
    span = trace.get_current_span()
    if span.is_recording(): span.set_attribute("media.file_path", file_path)
    return _send_task_to_ai(file_path, extract_series_title_ai_function)


@_logger.trace("identify_series_season_episode_with_open_ai")
def identify_series_season_episode_with_open_ai(file_path: str) -> Optional[str]:
    span = trace.get_current_span()
    if span.is_recording(): span.set_attribute("media.file_path", file_path)
    return _send_task_to_ai(file_path, extract_season_episode_from_filename)


@_logger.trace("_send_task_to_ai")
def _send_task_to_ai(file_path: str, ai_function: callable) -> Optional[str]:
    try:
        return _ask_open_ai(ai_input = _prepare_open_ai_input(file_path, ai_function))
    except Exception as e:
        _logger.error(f"Error extracting data for file [{file_path}]: {str(e)}")
        return None


def _prepare_open_ai_input(file_path: str, ai_function: callable) -> str:
    return f"""Output only the result as specified in the function comments below.
Function code:
```python
{inspect.getsource(ai_function)}
```
Input:
```plaintext
{file_path}
```"""


@_logger.trace("_ask_open_ai")
def _ask_open_ai(ai_input: str) -> Optional[str]:
    span = trace.get_current_span()
    if span.is_recording():
        span.set_attribute("ai.model", _open_ai_model)

    try:
        ai_sys_instructions = """You are an AI that implements Python functions as described in code comments.
Only respond to the user's request by executing the function as described, strictly following the output format specified in the comments. 
This is very important: you are forbidden from adding explanations, rephrasing, adding context, adding code blocks, or adding any extra text—output only the function result, as defined.
Think step by step and double-check your answer before responding, especially when the input is ambiguous or tricky.
You are forbidden from guessing, inferring, or deducing information that is not explicitly present in the user input or function comments."""

        client = _get_open_ai_client()
        if client is None:
            return None

        response = client.responses.create(
            model=_open_ai_model,
            instructions=ai_sys_instructions,
            input=ai_input,
            temperature=0.1)

        usage = _extract_usage_from_response(response.usage)

        if span.is_recording():
            for key, value in usage.items():
                span.set_attribute(f"ai.usage.{key}", value)

        logger = _get_openai_request_logger()
        if logger:
            logger.log(**usage)

        return response.output_text
    except RateLimitError as e:
        _logger.error(f"OpenAI rate limit exceeded. You're probably out of credits, bud. Error: {str(e)}")
        return None

    except Exception as e:
        _logger.error(f"Error communicating with OpenAI: {str(e)}")
        return None

def _extract_usage_from_response(usage):
    # I'm not sure if the all those properties will be present 100% of the time, so I need to work around it.
    input_tokens = getattr(usage, 'input_tokens', 0)
    input_tokens_details = getattr(usage, 'input_tokens_details', None)
    cached_tokens = getattr(input_tokens_details, 'cached_tokens', 0) if input_tokens_details else 0

    output_tokens = getattr(usage, 'output_tokens', None)
    output_token_details = getattr(usage, 'output_token_details', 0)
    reasoning_tokens = getattr(output_token_details, 'reasoning_tokens', 0) if output_token_details else 0

    total_tokens = getattr(usage, 'total_tokens', 0)

    return {
        'input_tokens': input_tokens,
        'cached_tokens': cached_tokens,
        'output_tokens': output_tokens,
        'reasoning_tokens': reasoning_tokens,
        'total_tokens': total_tokens
    }


def _get_openai_request_logger():
    global _openai_request_logger

    if _openai_request_logger is None:
        try:
            _openai_request_logger = get_repository("openai_logger")
        except ValueError as exc:
            _logger.error(f"Unable to initialise OpenAI logger repository: {exc}")
            return None
    return _openai_request_logger


def _get_open_ai_client():
    global _open_ai_client

    if _open_ai_client is not None:
        return _open_ai_client

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        _logger.error("OPENAI_API_KEY environment variable must be set to use OpenAI integrations.")
        return None

    organization = os.environ.get("OPENAI_ORGANIZATION")

    try:
        _open_ai_client = OpenAI(api_key=api_key, organization=organization)
    except OpenAIError as exc:
        _logger.error(f"Failed to initialise OpenAI client: {exc}")
        _open_ai_client = None

    return _open_ai_client
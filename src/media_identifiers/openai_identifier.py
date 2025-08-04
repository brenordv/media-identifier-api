import inspect
import os
from typing import Optional
from openai import OpenAI, RateLimitError
from simple_log_factory.log_factory import log_factory

from src.media_identifiers.ai_functions import extract_movie_title_ai_function, extract_series_title_ai_function
from src.media_identifiers.ai_functions.extract_media_type_ai_function import extract_media_type_from_filename
from src.media_identifiers.ai_functions.extract_season_episode_ai_function import extract_season_episode_from_filename
from src.models.media_info import MediaInfoBuilder
from src.repositories.repository_factory import get_repository

_open_ai_model = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
_logger = log_factory("MediaIdentifier", unique_handler_types=True)
_openai_request_logger = get_repository("openai_logger")
_open_ai_client = OpenAI(
    api_key=os.environ.get("OPENAI_API_KEY"),
    organization=os.environ.get("OPENAI_ORGANIZATION"),
)


def identify_media_with_open_ai(file_path: str, media_type: str) -> Optional[dict]:
    if media_type is None:
        media_type = _identify_media_type_with_open_ai(file_path)
        if not media_type:
            _logger.warning(f"Could not identify media type for file: {file_path}")
            return None

    if media_type == 'movie':
        title = _identify_movie_title_with_open_ai(file_path)
        season, episode = None, None
    else:
        title = _identify_series_title_with_open_ai(file_path)
        season, episode = _parse_season_episode(_identify_series_season_episode_with_open_ai(file_path))

    return MediaInfoBuilder() \
        .with_title(title) \
        .with_original_title(title) \
        .with_media_type(media_type) \
        .with_season(season) \
        .with_episode(episode) \
        .with_used_openai(True) \
        .build()


def _parse_season_episode(data):
    parts = data.split(',')
    if len(parts) != 2:
        _logger.error(f"Invalid season/episode format: {data}")
        return None, None

    season_parts = parts[0].strip().split(':')

    if len(season_parts) != 2 or not season_parts[1].isdigit():
        _logger.error(f"Invalid season format: {season_parts}")
        return None, None

    season = int(season_parts[1])

    episode_parts = parts[1].strip().split(':')

    if len(episode_parts) != 2 or not episode_parts[1].isdigit():
        _logger.error(f"Invalid episode format: {episode_parts}")
        return None, None

    episode = int(episode_parts[1])

    return season, episode


def _identify_media_type_with_open_ai(file_path: str) -> Optional[str]:
    return _send_task_to_ai(file_path, extract_media_type_from_filename)


def _identify_movie_title_with_open_ai(file_path: str) -> Optional[str]:
    return _send_task_to_ai(file_path, extract_movie_title_ai_function)


def _identify_series_title_with_open_ai(file_path: str) -> Optional[str]:
    return _send_task_to_ai(file_path, extract_series_title_ai_function)


def _identify_series_season_episode_with_open_ai(file_path: str) -> Optional[str]:
    return _send_task_to_ai(file_path, extract_season_episode_from_filename)


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


def _ask_open_ai(ai_input: str) -> Optional[str]:
    try:
        ai_sys_instructions = """You are an AI that implements Python functions as described in code comments.
Only respond to the user's request by executing the function as described, strictly following the output format specified in the comments. 
This is very important: you are forbidden from adding explanations, rephrasing, adding context, adding code blocks, or adding any extra text—output only the function result, as defined.
Think step by step and double-check your answer before responding, especially when the input is ambiguous or tricky.
You are forbidden from guessing, inferring, or deducing information that is not explicitly present in the user input or function comments."""

        response = _open_ai_client.responses.create(
            model=_open_ai_model,
            instructions=ai_sys_instructions,
            input=ai_input,
            temperature=0.1)

        usage = _extract_usage_from_response(response.usage)

        _openai_request_logger.log(**usage)

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
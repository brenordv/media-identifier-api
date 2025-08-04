from typing import Optional

from guessit import guessit
from simple_log_factory.log_factory import log_factory

from src.models.media_info import MediaInfoBuilder

_logger = log_factory("MediaIdentifier", unique_handler_types=True)

def identify_media_with_guess_it(file_path: str) -> Optional[dict]:
    try:
        _logger.debug(f"Identifying media file: {file_path}")

        metadata = guessit(file_path)

        return _create_record_from_guessit_data(metadata)
    except Exception as e:
        _logger.error(f"Error identifying media file {file_path}: {str(e)}")
        return None

def _create_record_from_guessit_data(guess_it_data):

    return MediaInfoBuilder()\
        .with_title(guess_it_data.get('title')) \
        .with_original_title(guess_it_data.get('title')) \
        .with_year(guess_it_data.get('year', None)) \
        .with_media_type(guess_it_data.get('type')) \
        .with_episode_title(guess_it_data.get('episode_title')) \
        .with_season(guess_it_data.get('season', None)) \
        .with_episode(guess_it_data.get('episode', None)) \
        .with_original_language(guess_it_data.get('original_language')) \
        .with_used_guessit(True) \
        .build()

from src.media_identifiers.media_identification_tasks.openai_tasks import openai_identify_series_season_and_episode_by_title
from src.media_identifiers.media_identification_tasks.tmdb_tasks import tmdb_identify_movie_by_id, \
    tmdb_get_movie_external_ids, tmdb_identify_series_by_title_and_id, tmdb_get_series_external_ids, tmdb_get_episode_details


def build_movie_identification_pipeline():
    return [
        tmdb_identify_movie_by_id,
        tmdb_get_movie_external_ids
    ]


def build_series_identification_pipeline():
    return [
        tmdb_identify_series_by_title_and_id,
        openai_identify_series_season_and_episode_by_title,
        tmdb_get_series_external_ids,
        tmdb_get_episode_details
    ]

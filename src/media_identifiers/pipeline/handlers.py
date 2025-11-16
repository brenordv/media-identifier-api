from src.media_identifiers.media_identification_tasks.guessit_tasks import identify_media_with_guess_it
from src.media_identifiers.media_identification_tasks.openai_tasks import (
    openai_identify_series_season_and_episode_by_title,
    openai_run_basic_identification_by_filename,
)
from src.media_identifiers.media_identification_tasks.tmdb_tasks import (
    tmdb_get_episode_details,
    tmdb_get_movie_external_ids,
    tmdb_get_series_external_ids,
    tmdb_identify_movie_by_id,
    tmdb_identify_series_by_title_and_id,
)
from src.media_identifiers.pipeline.base import PipelineContext, PipelineHandler, StepResult
from src.media_identifiers.media_type_helpers import (
    is_media_type_valid,
    is_movie,
    is_tv,
)
from src.models.media_identification_request import RequestMode


class CacheLookupHandler(PipelineHandler):
    def __init__(self, label: str = "cache_lookup"):
        self.label = label
        self.name = f"cache_lookup[{label}]"

    def handles(self, context: PipelineContext) -> bool:
        if context.completed:
            return False
        if context.media is None:
            return False
        if context.media.get("title") is None:
            return False
        if not is_media_type_valid(context.media.get("media_type")):
            return False
        return True

    def invoke(self, context: PipelineContext) -> StepResult:
        cached = context.cache_repository.get_cached_by_obj(context.media)
        if cached:
            context.logger.debug(f"[{self.name}] Cache hit; stopping pipeline.")
            context.mark_cached_result(cached)
            return StepResult.done(f"Cache hit during {self.label}")

        context.logger.debug(f"[{self.name}] No cached entry found.")
        return StepResult.success(f"No cache entry during {self.label}")


class GuessItIdentificationHandler(PipelineHandler):
    name = "guessit_identification"

    def handles(self, context: PipelineContext) -> bool:
        if context.mode != RequestMode.FILENAME:
            return False
        if not context.file_path:
            return False
        # Skip if we already have GuessIt information
        used_guessit = context.media.get("used_guessit") if context.media else False
        return not used_guessit

    def invoke(self, context: PipelineContext) -> StepResult:
        guessit_result = identify_media_with_guess_it(context.file_path)
        if not guessit_result:
            context.logger.debug("[guessit_identification] GuessIt did not return data.")
            return StepResult.skip("GuessIt returned no data.")

        context.update_media(guessit_result)
        context.logger.debug("[guessit_identification] GuessIt data merged into context.")
        return StepResult.success()


class OpenAIBasicIdentificationHandler(PipelineHandler):
    name = "openai_basic_identification"

    def handles(self, context: PipelineContext) -> bool:
        if context.mode != RequestMode.FILENAME:
            return False
        if not context.file_path:
            return False
        if context.media is None:
            return True
        if context.media.get("title") and is_media_type_valid(context.media.get("media_type")):
            return False
        return True

    def invoke(self, context: PipelineContext) -> StepResult:
        media_data, success = openai_run_basic_identification_by_filename(
            context.media,
            file_path=context.file_path,
        )
        if not success or media_data is None:
            context.logger.debug("[openai_basic_identification] OpenAI skipped or failed.")
            return StepResult.skip("OpenAI basic identification did not succeed.")

        context.update_media(media_data)
        context.logger.debug("[openai_basic_identification] OpenAI data merged into context.")
        return StepResult.success()


class OpenAISeriesSeasonEpisodeHandler(PipelineHandler):
    name = "openai_series_season_episode"

    def handles(self, context: PipelineContext) -> bool:
        if not is_tv(context.media_type):
            return False
        if context.media is None:
            return False
        if context.media.get("season") is not None and context.media.get("episode") is not None:
            return False
        if not context.file_path:
            return False
        return True

    def invoke(self, context: PipelineContext) -> StepResult:
        media_data, success = openai_identify_series_season_and_episode_by_title(
            context.media,
            file_path=context.file_path,
        )
        if not success or media_data is None:
            context.logger.debug("[openai_series_season_episode] OpenAI could not identify season/episode.")
            return StepResult.skip("OpenAI season/episode identification failed.")

        context.update_media(media_data)
        context.logger.debug("[openai_series_season_episode] Season/episode data merged.")
        return StepResult.success()


class TMDBIdentifyMovieHandler(PipelineHandler):
    name = "tmdb_identify_movie"

    def handles(self, context: PipelineContext) -> bool:
        if not is_movie(context.media_type):
            return False
        if context.media is None:
            return False
        if context.media.get("tmdb_id"):
            return False
        return True

    def invoke(self, context: PipelineContext) -> StepResult:
        media_data, success = tmdb_identify_movie_by_id(context.media)
        if not success or media_data is None:
            message = "[tmdb_identify_movie] Failed to identify movie via TMDB."
            context.logger.debug(message)
            return StepResult.fatal(message)

        context.update_media(media_data)
        context.logger.debug("[tmdb_identify_movie] TMDB movie data merged.")
        return StepResult.success()


class TMDBMovieExternalIdsHandler(PipelineHandler):
    name = "tmdb_movie_external_ids"

    def handles(self, context: PipelineContext) -> bool:
        if not is_movie(context.media_type):
            return False
        if context.media is None:
            return False
        if not context.media.get("tmdb_id"):
            return False
        return True

    def invoke(self, context: PipelineContext) -> StepResult:
        media_data, success = tmdb_get_movie_external_ids(context.media, success=True)
        if not success or media_data is None:
            context.logger.debug("[tmdb_movie_external_ids] Unable to fetch movie external IDs.")
            return StepResult.skip("Movie external IDs not available.")

        context.update_media(media_data)
        context.logger.debug("[tmdb_movie_external_ids] External IDs merged for movie.")
        return StepResult.success()


class TMDBIdentifySeriesHandler(PipelineHandler):
    name = "tmdb_identify_series"

    def handles(self, context: PipelineContext) -> bool:
        if not is_tv(context.media_type):
            return False
        if context.media is None:
            return False
        if context.media.get("tmdb_series_id"):
            return False
        return True

    def invoke(self, context: PipelineContext) -> StepResult:
        media_data, success = tmdb_identify_series_by_title_and_id(context.media)
        if not success or media_data is None:
            message = "[tmdb_identify_series] Failed to identify series via TMDB."
            context.logger.debug(message)
            return StepResult.fatal(message)

        context.update_media(media_data)
        context.logger.debug("[tmdb_identify_series] TMDB series data merged.")
        return StepResult.success()


class TMDBSeriesExternalIdsHandler(PipelineHandler):
    name = "tmdb_series_external_ids"

    def handles(self, context: PipelineContext) -> bool:
        if not is_tv(context.media_type):
            return False
        if context.media is None:
            return False
        if not context.media.get("tmdb_id"):
            return False
        return True

    def invoke(self, context: PipelineContext) -> StepResult:
        media_data, success = tmdb_get_series_external_ids(context.media, success=True)
        if not success or media_data is None:
            context.logger.debug("[tmdb_series_external_ids] Unable to fetch series external IDs.")
            return StepResult.skip("Series external IDs not available.")

        context.update_media(media_data)
        context.logger.debug("[tmdb_series_external_ids] External IDs merged for series.")
        return StepResult.success()


class TMDBEpisodeDetailsHandler(PipelineHandler):
    name = "tmdb_episode_details"

    def handles(self, context: PipelineContext) -> bool:
        if context.media_type != "tv":
            return False
        if context.media is None:
            return False
        if context.media.get("tmdb_id"):
            return False
        season = context.media.get("season")
        episode = context.media.get("episode")
        tmdb_series_id = context.media.get("tmdb_series_id")
        return tmdb_series_id is not None and season is not None and episode is not None

    def invoke(self, context: PipelineContext) -> StepResult:
        media_data, success = tmdb_get_episode_details(context.media, success=True)
        if not success or media_data is None:
            context.logger.debug("[tmdb_episode_details] Unable to fetch episode details.")
            return StepResult.skip("Episode details not available.")

        context.update_media(media_data)
        context.logger.debug("[tmdb_episode_details] Episode details merged.")
        return StepResult.success()


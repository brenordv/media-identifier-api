"""The identification steps: guessit, OpenAI, TMDB identification and enrichment, and cache lookups."""

from opentelemetry import trace

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
from src.media_identifiers.media_type_helpers import (
    has_media_type,
    is_media_type_valid,
    is_movie,
    is_tv,
)
from src.media_identifiers.pipeline.base import PipelineContext, PipelineHandler, StepResult
from src.models.media_identification_request import RequestMode
from src.utils import get_otel_log_handler

_logger = get_otel_log_handler("PipelineHandlers")

_NO_MEDIA = "No media in context."
_NO_FILE_PATH = "No file path in context."


class CacheLookupHandler(PipelineHandler):
    """Ends the run with the cached record when the media identified so far is already cached.

    Args:
        label: Which point of the pipeline this lookup sits at (used in logs and span attributes).
    """

    def __init__(self, label: str = "cache_lookup") -> None:
        self.label = label
        self.name = f"cache_lookup[{label}]"

    def handles(self, context: PipelineContext) -> bool:
        """Applies while the run is open and the media has a title and a valid media type."""
        if context.completed:
            return False
        if context.media is None:
            return False
        if context.media.get("title") is None:
            return False
        if not is_media_type_valid(context.media.get("media_type")):
            return False
        return True

    @_logger.trace("CacheLookupHandler.invoke")
    def invoke(self, context: PipelineContext) -> StepResult:
        """Look the media up; DONE on a hit, SUCCESS otherwise (a hit of another media type is discarded)."""
        media = context.media
        if media is None:
            return StepResult.skip(_NO_MEDIA)

        span = trace.get_current_span()
        if span.is_recording():
            span.set_attributes(
                {
                    "pipeline.handler": self.name,
                    "media.title": media.get("title"),
                    "media.type": media.get("media_type"),
                }
            )
        cached = context.cache_repository.get_cached_by_obj(media)
        if cached and not has_media_type(cached, media.get("media_type")):
            context.logger.warning(
                f"[{self.name}] Discarded cache hit of another media type: identified {media.get('media_type')!r}, "
                f"cached row {cached.get('id')} is {cached.get('media_type')!r} with TMDb ID {cached.get('tmdb_id')}."
            )
            cached = None

        if cached:
            context.logger.debug(f"[{self.name}] Cache hit; stopping pipeline.")
            context.mark_cached_result(cached)
            return StepResult.done(f"Cache hit during {self.label}")

        context.logger.debug(f"[{self.name}] No cached entry found.")
        return StepResult.success(f"No cache entry during {self.label}")


class GuessItIdentificationHandler(PipelineHandler):
    """Parses the file name with guessit."""

    name = "guessit_identification"

    def handles(self, context: PipelineContext) -> bool:
        """Applies to filename requests that guessit has not processed yet."""
        if context.mode != RequestMode.FILENAME:
            return False
        if not context.file_path:
            return False
        used_guessit = context.media.get("used_guessit") if context.media else False
        return not used_guessit

    @_logger.trace("GuessItIdentificationHandler.invoke")
    def invoke(self, context: PipelineContext) -> StepResult:
        """Merge guessit's title, type, year, season and episode into the context."""
        file_path = context.file_path
        if not file_path:
            return StepResult.skip(_NO_FILE_PATH)

        span = trace.get_current_span()
        if span.is_recording():
            span.set_attributes({"pipeline.handler": self.name, "media.file_path": file_path})
        guessit_result = identify_media_with_guess_it(file_path)
        if not guessit_result:
            context.logger.debug("[guessit_identification] GuessIt did not return data.")
            return StepResult.skip("GuessIt returned no data.")

        context.update_media(guessit_result)
        context.logger.debug("[guessit_identification] GuessIt data merged into context.")
        return StepResult.success()


class OpenAIBasicIdentificationHandler(PipelineHandler):
    """Asks OpenAI for the media type and title when guessit did not find both."""

    name = "openai_basic_identification"

    def handles(self, context: PipelineContext) -> bool:
        """Applies to filename requests still missing a title or a valid media type."""
        if context.mode != RequestMode.FILENAME:
            return False
        if not context.file_path:
            return False
        if context.media is None:
            return True
        if context.media.get("title") and is_media_type_valid(context.media.get("media_type")):
            return False
        return True

    @_logger.trace("OpenAIBasicIdentificationHandler.invoke")
    def invoke(self, context: PipelineContext) -> StepResult:
        """Merge OpenAI's media type and title into the context."""
        file_path = context.file_path
        if not file_path:
            return StepResult.skip(_NO_FILE_PATH)

        span = trace.get_current_span()
        if span.is_recording():
            span.set_attributes({"pipeline.handler": self.name, "media.file_path": file_path})
        media_data, success = openai_run_basic_identification_by_filename(context.media, file_path=file_path)
        if not success or media_data is None:
            context.logger.debug("[openai_basic_identification] OpenAI skipped or failed.")
            return StepResult.skip("OpenAI basic identification did not succeed.")

        context.update_media(media_data)
        context.logger.debug("[openai_basic_identification] OpenAI data merged into context.")
        return StepResult.success()


class OpenAISeriesSeasonEpisodeHandler(PipelineHandler):
    """Asks OpenAI for the season and episode of a TV file when they are still unknown."""

    name = "openai_series_season_episode"

    def handles(self, context: PipelineContext) -> bool:
        """Applies to TV media with a file path and without both season and episode."""
        if not is_tv(context.media_type):
            return False
        if context.media is None:
            return False
        if context.media.get("season") is not None and context.media.get("episode") is not None:
            return False
        if not context.file_path:
            return False
        return True

    @_logger.trace("OpenAISeriesSeasonEpisodeHandler.invoke")
    def invoke(self, context: PipelineContext) -> StepResult:
        """Merge OpenAI's season and episode into the context."""
        media = context.media
        file_path = context.file_path
        if media is None or not file_path:
            return StepResult.skip(_NO_MEDIA)

        span = trace.get_current_span()
        if span.is_recording():
            span.set_attributes({"pipeline.handler": self.name, "media.file_path": file_path})
        media_data, success = openai_identify_series_season_and_episode_by_title(media, file_path=file_path)
        if not success or media_data is None:
            context.logger.debug("[openai_series_season_episode] OpenAI could not identify season/episode.")
            return StepResult.skip("OpenAI season/episode identification failed.")

        context.update_media(media_data)
        context.logger.debug("[openai_series_season_episode] Season/episode data merged.")
        return StepResult.success()


class TMDBIdentifyMovieHandler(PipelineHandler):
    """Finds the movie on TMDB and merges its details; the run aborts when TMDB has no match."""

    name = "tmdb_identify_movie"

    def handles(self, context: PipelineContext) -> bool:
        """Applies to movies without a TMDB id yet."""
        if not is_movie(context.media_type):
            return False
        if context.media is None:
            return False
        if context.media.get("tmdb_id"):
            return False
        return True

    @_logger.trace("TMDBIdentifyMovieHandler.invoke")
    def invoke(self, context: PipelineContext) -> StepResult:
        """Search TMDB by title and year, then fetch the movie's details."""
        media = context.media
        if media is None:
            return StepResult.skip(_NO_MEDIA)

        span = trace.get_current_span()
        if span.is_recording():
            span.set_attributes({"pipeline.handler": self.name, "media.title": media.get("title")})
        media_data, success = tmdb_identify_movie_by_id(media)
        if not success or media_data is None:
            message = "[tmdb_identify_movie] Failed to identify movie via TMDB."
            context.logger.debug(message)
            return StepResult.fatal(message)

        context.update_media(media_data)
        context.logger.debug("[tmdb_identify_movie] TMDB movie data merged.")
        return StepResult.success()


class TMDBMovieExternalIdsHandler(PipelineHandler):
    """Adds IMDb and other external ids to an identified movie."""

    name = "tmdb_movie_external_ids"

    def handles(self, context: PipelineContext) -> bool:
        """Applies to movies with a TMDB id."""
        if not is_movie(context.media_type):
            return False
        if context.media is None:
            return False
        if not context.media.get("tmdb_id"):
            return False
        return True

    @_logger.trace("TMDBMovieExternalIdsHandler.invoke")
    def invoke(self, context: PipelineContext) -> StepResult:
        """Fetch and merge the movie's external ids; SKIP when TMDB has none."""
        media = context.media
        if media is None:
            return StepResult.skip(_NO_MEDIA)

        span = trace.get_current_span()
        if span.is_recording():
            span.set_attributes({"pipeline.handler": self.name, "tmdb.id": media.get("tmdb_id")})
        media_data, success = tmdb_get_movie_external_ids(media, success=True)
        if not success or media_data is None:
            context.logger.debug("[tmdb_movie_external_ids] Unable to fetch movie external IDs.")
            return StepResult.skip("Movie external IDs not available.")

        context.update_media(media_data)
        context.logger.debug("[tmdb_movie_external_ids] External IDs merged for movie.")
        return StepResult.success()


class TMDBIdentifySeriesHandler(PipelineHandler):
    """Finds the series on TMDB and merges its details; the run aborts when TMDB has no match."""

    name = "tmdb_identify_series"

    def handles(self, context: PipelineContext) -> bool:
        """Applies to TV media without a TMDB series id yet."""
        if not is_tv(context.media_type):
            return False
        if context.media is None:
            return False
        if context.media.get("tmdb_series_id"):
            return False
        return True

    @_logger.trace("TMDBIdentifySeriesHandler.invoke")
    def invoke(self, context: PipelineContext) -> StepResult:
        """Search TMDB by title and year, then fetch the series' details."""
        media = context.media
        if media is None:
            return StepResult.skip(_NO_MEDIA)

        span = trace.get_current_span()
        if span.is_recording():
            span.set_attributes({"pipeline.handler": self.name, "media.title": media.get("title")})
        media_data, success = tmdb_identify_series_by_title_and_id(media)
        if not success or media_data is None:
            message = "[tmdb_identify_series] Failed to identify series via TMDB."
            context.logger.debug(message)
            return StepResult.fatal(message)

        context.update_media(media_data)
        context.logger.debug("[tmdb_identify_series] TMDB series data merged.")
        return StepResult.success()


class TMDBSeriesExternalIdsHandler(PipelineHandler):
    """Adds the series' IMDb and other external ids to a TV record."""

    name = "tmdb_series_external_ids"

    def handles(self, context: PipelineContext) -> bool:
        """Applies to TV media with a TMDB series id."""
        if not is_tv(context.media_type):
            return False
        if context.media is None:
            return False
        if not context.media.get("tmdb_series_id"):
            return False
        return True

    @_logger.trace("TMDBSeriesExternalIdsHandler.invoke")
    def invoke(self, context: PipelineContext) -> StepResult:
        """Fetch and merge the series' external ids; SKIP when TMDB has none."""
        media = context.media
        if media is None:
            return StepResult.skip(_NO_MEDIA)

        span = trace.get_current_span()
        if span.is_recording():
            span.set_attributes({"pipeline.handler": self.name, "tmdb.series_id": media.get("tmdb_series_id")})
        media_data, success = tmdb_get_series_external_ids(media, success=True)
        if not success or media_data is None:
            context.logger.debug("[tmdb_series_external_ids] Unable to fetch series external IDs.")
            return StepResult.skip("Series external IDs not available.")

        context.update_media(media_data)
        context.logger.debug("[tmdb_series_external_ids] External IDs merged for series.")
        return StepResult.success()


class TMDBEpisodeDetailsHandler(PipelineHandler):
    """Adds the episode's TMDB id, title, overview and air year to a TV record."""

    name = "tmdb_episode_details"

    def handles(self, context: PipelineContext) -> bool:
        """Applies to TV media with series id, season and episode, and no TMDB id yet."""
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

    @_logger.trace("TMDBEpisodeDetailsHandler.invoke")
    def invoke(self, context: PipelineContext) -> StepResult:
        """Fetch and merge the episode's details; SKIP when TMDB has none."""
        media = context.media
        if media is None:
            return StepResult.skip(_NO_MEDIA)

        span = trace.get_current_span()
        if span.is_recording():
            span.set_attributes(
                {
                    "pipeline.handler": self.name,
                    "tmdb.series_id": media.get("tmdb_series_id"),
                    "media.season": media.get("season"),
                    "media.episode": media.get("episode"),
                }
            )
        media_data, success = tmdb_get_episode_details(media, success=True)
        if not success or media_data is None:
            context.logger.debug("[tmdb_episode_details] Unable to fetch episode details.")
            return StepResult.skip("Episode details not available.")

        context.update_media(media_data)
        context.logger.debug("[tmdb_episode_details] Episode details merged.")
        return StepResult.success()

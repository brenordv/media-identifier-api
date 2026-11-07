"""The identification steps: guessit, Nimble triage, the OpenAI fallback, TMDB identification and enrichment, and
cache lookups."""

from typing import Any, Literal

from opentelemetry import trace

from src.converters.create_searchable_reference import create_searchable_reference
from src.media_identifiers.constants import MOVIE, TV
from src.media_identifiers.errors import UpstreamUnavailableError
from src.media_identifiers.media_identification_tasks.guessit_tasks import identify_media_with_guess_it
from src.media_identifiers.media_identification_tasks.tmdb_tasks import (
    tmdb_get_episode_details,
    tmdb_get_movie_external_ids,
    tmdb_get_series_external_ids,
    tmdb_identify_movie_by_id,
    tmdb_identify_series_by_title_and_id,
)
from src.media_identifiers.media_type_helpers import (
    is_media_type_valid,
    is_movie,
    is_record_of_media_type,
    is_tv,
    normalize_media_type,
)
from src.media_identifiers.nimble_classifier import classify_media_kind
from src.media_identifiers.openai_identifier import OpenAIMediaGuess, identify_media_with_openai, is_openai_configured
from src.media_identifiers.pipeline.base import PipelineContext, PipelineHandler, StepResult
from src.models.media_identification_request import RequestMode
from src.models.media_info import MediaData
from src.utils import get_otel_log_handler

_logger = get_otel_log_handler("PipelineHandlers")

_NO_MEDIA = "No media in context."
_NO_FILE_PATH = "No file path in context."
_READING_KEYS = ("media_type", "title", "year", "season", "episode")

OpenAITrigger = Literal["type_uncertain", "no_title", "tv_missing_season", "tmdb_no_match"]


def _reading(media: MediaData | None) -> dict[str, Any]:
    """The media type, title, year, season and episode identified so far."""
    return {key: (media or {}).get(key) for key in _READING_KEYS}


def _tmdb_search_key(media_type: str, media: MediaData) -> tuple[str, str | None, int | None]:
    title = media.get("title")
    return media_type, title.casefold() if isinstance(title, str) else None, media.get("year")


def _title_key(title: object) -> str | None:
    reference = create_searchable_reference(title) if isinstance(title, str) else None
    return reference.casefold() if reference else None


def _without_episode_numbers(media: MediaData) -> MediaData:
    """The record without season and episode, which a movie does not have."""
    return {**media, "season": None, "episode": None}


def _confirms_openai_title(context: PipelineContext, searched: MediaData, matched: MediaData) -> bool:
    """True unless the searched title came from OpenAI and TMDB's match carries another title.

    TMDB search returns its closest result for almost any query, so a title OpenAI suggested only counts when TMDB's
    title or original title is the same title (compared as search keys).
    """
    if not context.title_from_openai:
        return True
    wanted = _title_key(searched.get("title"))
    return wanted is not None and wanted in {
        _title_key(matched.get("title")),
        _title_key(matched.get("original_title")),
    }


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
        if cached and not is_record_of_media_type(cached, media.get("media_type")):
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
        context.guessit_reading = _reading(guessit_result) if guessit_result else None
        context.step_readings["guessit"] = repr(context.guessit_reading)
        if not guessit_result:
            context.logger.debug("[guessit_identification] GuessIt did not return data.")
            return StepResult.skip("GuessIt returned no data.")

        context.update_media(guessit_result)
        if is_media_type_valid(context.media_type):
            context.decided_by = "guessit"
        context.logger.debug("[guessit_identification] GuessIt data merged into context.")
        return StepResult.success()


class NimbleTriageHandler(PipelineHandler):
    """Asks the Nimble classifier whether the file is a movie, a TV release, or neither.

    A confident "other" ends the run as not media; a confident movie or TV verdict sets the media type. A verdict
    below the confidence threshold that disagrees with guessit sets ``type_uncertain``.
    """

    name = "nimble_triage"

    def handles(self, context: PipelineContext) -> bool:
        """Applies to filename requests while the run is open."""
        return context.mode == RequestMode.FILENAME and bool(context.file_path) and not context.completed

    @_logger.trace("NimbleTriageHandler.invoke")
    def invoke(self, context: PipelineContext) -> StepResult:
        """Classify the file path and apply the verdict."""
        file_path = context.file_path
        if not file_path:
            return StepResult.skip(_NO_FILE_PATH)

        verdict = classify_media_kind(file_path)
        context.nimble_verdict = verdict
        if verdict is None:
            context.step_readings["nimble"] = "no verdict"
            return StepResult.skip("Nimble gave no verdict.")

        context.step_readings["nimble"] = f"{verdict.choice} ({verdict.confidence:.2f})"
        guessit_type = normalize_media_type(context.media_type)

        if not verdict.is_confident:
            context.type_uncertain = guessit_type is not None and verdict.choice != guessit_type
            return StepResult.skip("Nimble is not confident.")

        if verdict.choice == "other":
            context.logger.info(
                f"Nimble says {file_path!r} is not a movie or TV release (confidence {verdict.confidence:.2f})."
            )
            context.mark_not_media("nimble")
            return StepResult.done("Not a movie or TV release.")

        if verdict.choice != guessit_type:
            media = {**(context.media or {}), "media_type": verdict.choice, "used_nimble": True}
            context.media = _without_episode_numbers(media) if verdict.choice == MOVIE else media
            context.decided_by = "nimble"
        return StepResult.success()


class OpenAIFallbackHandler(PipelineHandler):
    """Asks OpenAI, at most once per run, when the earlier steps leave a gap.

    Before TMDB identification it covers an uncertain media type, a missing title and TV without a season; after it,
    a TMDB search that found nothing. It updates the media type, title, year, season and episode, and never sets a
    TMDB id.

    Args:
        after_tmdb: True for the position after TMDB identification.
    """

    def __init__(self, after_tmdb: bool) -> None:
        self.after_tmdb = after_tmdb
        self.name = "openai_fallback[post-tmdb]" if after_tmdb else "openai_fallback[pre-tmdb]"

    def handles(self, context: PipelineContext) -> bool:
        """Applies to open filename runs that have not consulted OpenAI and have a gap OpenAI may fill."""
        if context.mode != RequestMode.FILENAME or not context.file_path or context.completed:
            return False
        if context.openai_consulted or not is_openai_configured():
            return False
        return self._trigger(context) is not None

    def _trigger(self, context: PipelineContext) -> OpenAITrigger | None:
        media = context.media or {}
        if self.after_tmdb:
            identified = media.get("tmdb_series_id") if is_tv(context.media_type) else media.get("tmdb_id")
            return "tmdb_no_match" if context.tmdb_no_match and not identified else None
        if context.type_uncertain or not is_media_type_valid(context.media_type):
            return "type_uncertain"
        if not media.get("title"):
            return "no_title"
        if is_tv(context.media_type) and media.get("season") is None:
            return "tv_missing_season"
        return None

    @_logger.trace("OpenAIFallbackHandler.invoke")
    def invoke(self, context: PipelineContext) -> StepResult:
        """Ask OpenAI and apply its answer; DONE when OpenAI says the file is not media.

        Raises:
            UpstreamUnavailableError: If OpenAI is unavailable and the media has nothing TMDB could search with yet
                (no title or no valid type), or this is the position after TMDB. Before TMDB, with a searchable
                record, the error is kept on the context instead and the run goes on.
        """
        file_path = context.file_path
        trigger = self._trigger(context)
        if not file_path or trigger is None:
            return StepResult.skip("Nothing for OpenAI to do.")

        context.openai_consulted = True
        span = trace.get_current_span()
        if span.is_recording():
            span.set_attributes({"pipeline.handler": self.name, "openai.trigger": trigger})

        try:
            identification = identify_media_with_openai(file_path, self._hints(context, trigger))
        except UpstreamUnavailableError as error:
            media = context.media or {}
            if self.after_tmdb or not media.get("title") or not is_media_type_valid(context.media_type):
                raise
            context.deferred_upstream_error = error
            context.step_readings["openai"] = f"unavailable ({trigger}): {error.cause_label}"
            context.logger.warning(
                f"OpenAI is unavailable ({error.cause_label}); identifying {file_path!r} without it."
            )
            return StepResult.skip("OpenAI is unavailable.")
        guess = identification.guess
        context.step_readings["openai"] = f"{identification.result} ({trigger})" + (
            f": {guess.model_dump()!r}" if guess else ""
        )
        if guess is None:
            return StepResult.skip("OpenAI did not know.")

        if guess.media_type == "other":
            context.logger.info(f"OpenAI says {file_path!r} is not a movie or TV release.")
            context.mark_not_media("openai")
            return StepResult.done("Not a movie or TV release.")

        self._apply(context, guess)
        return StepResult.success()

    @staticmethod
    def _hints(context: PipelineContext, trigger: OpenAITrigger) -> dict[str, Any]:
        verdict = context.nimble_verdict
        hints: dict[str, Any] = {
            "guessit": context.guessit_reading,
            "nimble": {"choice": verdict.choice, "confidence": verdict.confidence} if verdict else None,
            "trigger": trigger,
        }
        if trigger == "tmdb_no_match":
            media = context.media or {}
            hints["searched"] = {"title": media.get("title"), "year": media.get("year")}
        return hints

    @staticmethod
    def _apply(context: PipelineContext, guess: OpenAIMediaGuess) -> None:
        media = dict(context.media or {})
        previous_type = normalize_media_type(media.get("media_type"))

        media["media_type"] = guess.media_type
        media["year"] = guess.year
        if guess.title is not None and _title_key(guess.title) != _title_key(media.get("title")):
            media["title"] = guess.title
            media["searchable_reference"] = create_searchable_reference(guess.title)
            context.title_from_openai = True
        if guess.season is not None:
            media["season"] = guess.season
        if guess.episode is not None:
            media["episode"] = guess.episode
        media["used_openai"] = True

        if guess.media_type != previous_type:
            context.decided_by = "openai"
        verdict = context.nimble_verdict
        if media.get("used_nimble") and (verdict is None or verdict.choice != guess.media_type):
            media["used_nimble"] = False

        context.media = _without_episode_numbers(media) if guess.media_type == MOVIE else media


def _tmdb_miss(context: PipelineContext, kind: str, searched: MediaData, matched: MediaData | None) -> StepResult:
    """Record a TMDB search without a confirmed match and skip."""
    context.tmdb_no_match = True
    title = searched.get("title")
    if matched is None:
        context.step_readings["tmdb"] = f"no {kind} match for {title!r} ({searched.get('year')!r})"
    else:
        context.step_readings["tmdb"] = f"{kind} match {matched.get('title')!r} rejected for OpenAI's title {title!r}"
    return StepResult.skip(f"TMDB found no {kind}.")


class TMDBIdentifyMovieHandler(PipelineHandler):
    """Finds the movie on TMDB and merges its details; a search without a confirmed match sets ``tmdb_no_match``."""

    name = "tmdb_identify_movie"

    def handles(self, context: PipelineContext) -> bool:
        """Applies to titled movies without a TMDB id whose search has not run yet."""
        if not is_movie(context.media_type):
            return False
        media = context.media
        if media is None or not media.get("title"):
            return False
        if media.get("tmdb_id"):
            return False
        return _tmdb_search_key(MOVIE, media) not in context.tmdb_searches

    @_logger.trace("TMDBIdentifyMovieHandler.invoke")
    def invoke(self, context: PipelineContext) -> StepResult:
        """Search TMDB by title and year, then fetch the movie's details."""
        media = context.media
        if media is None:
            return StepResult.skip(_NO_MEDIA)

        span = trace.get_current_span()
        if span.is_recording():
            span.set_attributes({"pipeline.handler": self.name, "media.title": media.get("title")})
        context.tmdb_searches.add(_tmdb_search_key(MOVIE, media))
        media_data, success = tmdb_identify_movie_by_id(media)
        if not success or media_data is None:
            return _tmdb_miss(context, MOVIE, media, None)
        if not _confirms_openai_title(context, media, media_data):
            return _tmdb_miss(context, MOVIE, media, media_data)

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
    """Finds the series on TMDB and merges its details; a search without a confirmed match sets ``tmdb_no_match``."""

    name = "tmdb_identify_series"

    def handles(self, context: PipelineContext) -> bool:
        """Applies to titled TV media without a TMDB series id whose search has not run yet."""
        if not is_tv(context.media_type):
            return False
        media = context.media
        if media is None or not media.get("title"):
            return False
        if media.get("tmdb_series_id"):
            return False
        return _tmdb_search_key(TV, media) not in context.tmdb_searches

    @_logger.trace("TMDBIdentifySeriesHandler.invoke")
    def invoke(self, context: PipelineContext) -> StepResult:
        """Search TMDB by title and year, then fetch the series' details."""
        media = context.media
        if media is None:
            return StepResult.skip(_NO_MEDIA)

        span = trace.get_current_span()
        if span.is_recording():
            span.set_attributes({"pipeline.handler": self.name, "media.title": media.get("title")})
        context.tmdb_searches.add(_tmdb_search_key(TV, media))
        media_data, success = tmdb_identify_series_by_title_and_id(media)
        if not success or media_data is None:
            return _tmdb_miss(context, "series", media, None)
        if not _confirms_openai_title(context, media, media_data):
            return _tmdb_miss(context, "series", media, media_data)

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

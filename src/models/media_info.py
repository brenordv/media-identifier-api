"""The media record: its builder, the merge rule for partial records, and TMDB genre names."""

from datetime import datetime
from typing import Any, Self
from uuid import UUID

from src.converters.create_searchable_reference import create_searchable_reference
from src.media_identifiers.media_type_helpers import normalize_media_type

MediaData = dict[str, Any]
"""A media record: the keys :meth:`MediaInfoBuilder.build` produces, possibly with a subset filled."""

_SERVICE_FLAGS = ("used_guessit", "used_tmdb", "used_openai")

TMDB_GENRES: dict[int, str] = {
    28: "Action",
    12: "Adventure",
    16: "Animation",
    35: "Comedy",
    80: "Crime",
    99: "Documentary",
    18: "Drama",
    10751: "Family",
    14: "Fantasy",
    36: "History",
    27: "Horror",
    10402: "Music",
    9648: "Mystery",
    10749: "Romance",
    878: "Science Fiction",
    10770: "TV Movie",
    53: "Thriller",
    10752: "War",
    37: "Western",
    10759: "Action & Adventure",
    10762: "Kids",
    10763: "News",
    10764: "Reality",
    10765: "Sci-Fi & Fantasy",
    10766: "Soap",
    10767: "Talk",
    10768: "War & Politics",
}
"""TMDB genre ids (movie and TV lists) mapped to their names."""


class MediaInfoBuilder:
    """Fluent builder for :data:`MediaData` records; every ``with_*`` method returns the builder."""

    def __init__(self) -> None:
        self._id: UUID | str | None = None
        self._searchable_reference: str | None = None
        self._tmdb_id: int | None = None
        self._tmdb_series_id: int | None = None
        self._imdb_id: str | None = None
        self._tvdb_id: int | None = None
        self._tvrage_id: int | None = None
        self._wikidata_id: str | None = None
        self._facebook_id: str | None = None
        self._instagram_id: str | None = None
        self._twitter_id: str | None = None
        self._genres: list[str] | None = None
        self._title: str | None = None
        self._original_title: str | None = None
        self._overview: str | None = None
        self._episode_title: str | None = None
        self._season: int | None = None
        self._episode: int | None = None
        self._original_language: str | None = None
        self._media_type: str | None = None
        self._year: int | None = None
        self._tagline: str | None = None
        self._used_guessit: bool | None = None
        self._used_tmdb: bool | None = None
        self._used_openai: bool | None = None
        self._created_at: datetime | None = None
        self._modified_at: datetime | None = None

    def with_id(self, record_id: UUID | str | None) -> Self:
        """Set the cache record id."""
        self._id = record_id
        return self

    def with_searchable_reference(self, searchable_reference: str | None) -> Self:
        """Set the normalized search key derived from ``searchable_reference``; blank values are ignored."""
        if searchable_reference is None or searchable_reference.strip() == "":
            return self

        self._searchable_reference = create_searchable_reference(searchable_reference)
        return self

    def with_tmdb_id(self, tmdb_id: int | None) -> Self:
        """Set the TMDB id of the record's own entity (a movie, or a TV episode)."""
        self._tmdb_id = tmdb_id
        return self

    def with_tmdb_series_id(self, tmdb_series_id: int | None) -> Self:
        """Set the TMDB id of the series a TV episode belongs to."""
        self._tmdb_series_id = tmdb_series_id
        return self

    def with_imdb_id(self, imdb_id: str | None) -> Self:
        """Set the IMDb id."""
        self._imdb_id = imdb_id
        return self

    def with_tvdb_id(self, tvdb_id: int | None) -> Self:
        """Set the TheTVDB id."""
        self._tvdb_id = tvdb_id
        return self

    def with_tvrage_id(self, tvrage_id: int | None) -> Self:
        """Set the TVRage id."""
        self._tvrage_id = tvrage_id
        return self

    def with_wikidata_id(self, wikidata_id: str | None) -> Self:
        """Set the Wikidata id."""
        self._wikidata_id = wikidata_id
        return self

    def with_facebook_id(self, facebook_id: str | None) -> Self:
        """Set the Facebook id."""
        self._facebook_id = facebook_id
        return self

    def with_instagram_id(self, instagram_id: str | None) -> Self:
        """Set the Instagram id."""
        self._instagram_id = instagram_id
        return self

    def with_twitter_id(self, twitter_id: str | None) -> Self:
        """Set the Twitter id."""
        self._twitter_id = twitter_id
        return self

    def with_genres(self, genres: object) -> Self:
        """Set genres from TMDB data: a list of genre ids or of ``{"name": ...}`` dicts.

        Unknown ids and dicts without a name are skipped; an empty value clears the genres, and a value that is not a
        list is ignored.
        """
        if not genres:
            self._genres = None
            return self

        if not isinstance(genres, list):
            return self

        parsed_genres: set[str] = set()
        for genre in genres:
            if isinstance(genre, dict):
                if "name" in genre:
                    parsed_genres.add(genre["name"])
            elif isinstance(genre, int) and genre in TMDB_GENRES:
                parsed_genres.add(TMDB_GENRES[genre])

        self._genres = list(parsed_genres)
        return self

    def with_title(self, title: str | None) -> Self:
        """Set the title."""
        self._title = title
        return self

    def with_original_title(self, original_title: str | None) -> Self:
        """Set the title in the original language."""
        self._original_title = original_title
        return self

    def with_overview(self, overview: str | None) -> Self:
        """Set the synopsis."""
        self._overview = overview
        return self

    def with_episode_title(self, episode_title: str | None) -> Self:
        """Set the episode title."""
        self._episode_title = episode_title
        return self

    def with_season(self, season: int | None) -> Self:
        """Set the season number."""
        self._season = season
        return self

    def with_episode(self, episode: int | None) -> Self:
        """Set the episode number."""
        self._episode = episode
        return self

    def with_original_language(self, original_language: str | None) -> Self:
        """Set the original language code."""
        self._original_language = original_language
        return self

    def with_media_type(self, media_type: str | None) -> Self:
        """Set the media type, normalized to ``movie`` or ``tv``; anything else becomes ``unknown``."""
        normalized = normalize_media_type(media_type)
        self._media_type = normalized if normalized else "unknown"
        return self

    def with_year(self, year: int | None) -> Self:
        """Set the release year (for a TV episode, the year it aired)."""
        self._year = year
        return self

    def with_tagline(self, tagline: str | None) -> Self:
        """Set the tagline."""
        self._tagline = tagline
        return self

    def with_used_guessit(self, used_guessit: bool | None) -> Self:
        """Record whether guessit contributed to the record."""
        self._used_guessit = used_guessit
        return self

    def with_used_tmdb(self, used_tmdb: bool | None) -> Self:
        """Record whether TMDB contributed to the record."""
        self._used_tmdb = used_tmdb
        return self

    def with_used_openai(self, used_openai: bool | None) -> Self:
        """Record whether OpenAI contributed to the record."""
        self._used_openai = used_openai
        return self

    def with_created_at(self, created_at: datetime | None) -> Self:
        """Set the creation timestamp."""
        self._created_at = created_at
        return self

    def with_modified_at(self, modified_at: datetime | None) -> Self:
        """Set the last-modified timestamp."""
        self._modified_at = modified_at
        return self

    def build(self) -> MediaData:
        """Return the record with every key present; unset values are None."""
        return {
            "id": self._id,
            "searchable_reference": self._searchable_reference,
            "tmdb_id": self._tmdb_id,
            "imdb_id": self._imdb_id,
            "tmdb_series_id": self._tmdb_series_id,
            "tvdb_id": self._tvdb_id,
            "tvrage_id": self._tvrage_id,
            "wikidata_id": self._wikidata_id,
            "facebook_id": self._facebook_id,
            "instagram_id": self._instagram_id,
            "twitter_id": self._twitter_id,
            "genres": self._genres,
            "title": self._title,
            "original_title": self._original_title,
            "overview": self._overview,
            "episode_title": self._episode_title,
            "season": self._season,
            "episode": self._episode,
            "original_language": self._original_language,
            "media_type": self._media_type,
            "year": self._year,
            "tagline": self._tagline,
            "used_guessit": self._used_guessit,
            "used_tmdb": self._used_tmdb,
            "used_openai": self._used_openai,
            "created_at": self._created_at,
            "modified_at": self._modified_at,
        }


def merge_media_info(existing: MediaData | None, new: MediaData | None) -> MediaData | None:
    """Overlay ``new`` on ``existing`` and return the result as a new dict.

    None values in ``new`` never overwrite, and a ``used_*`` flag that is already True stays True.

    Args:
        existing: The record so far.
        new: Values to merge in.

    Returns:
        The merged record, or None when both inputs are None.
    """
    if existing is None:
        return new.copy() if new is not None else None

    merged = existing.copy()

    if new is None:
        return merged

    for key, value in new.items():
        if value is None:
            continue

        if key in _SERVICE_FLAGS and merged.get(key) is True:
            continue

        merged[key] = value
    return merged


def is_media_type_valid(media_type: str | None) -> bool:
    """Tell whether ``media_type`` normalizes to ``movie`` or ``tv``."""
    return normalize_media_type(media_type) is not None

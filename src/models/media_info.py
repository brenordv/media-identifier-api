from datetime import datetime
from typing import Union, List, Optional
from uuid import uuid4

from src.converters.create_searchable_reference import create_searchable_reference
from src.media_identifiers.media_type_helpers import normalize_media_type


class MediaInfoBuilder:
    def __init__(self):
        self._id: Union[uuid4, None] = None
        self._searchable_reference: Union[str, None] = None
        self._tmdb_id: Union[int, None] = None
        self._tmdb_series_id: Union[int, None] = None
        self._imdb_id: Union[str, None] = None
        self._tvdb_id: Union[int, None] = None
        self._tvrage_id: Union[int, None] = None
        self._wikidata_id: Union[str, None] = None
        self._facebook_id: Union[str, None] = None
        self._instagram_id: Union[str, None] = None
        self._twitter_id: Union[str, None] = None
        self._genres: Union[List[str], None] = None
        self._title: Union[str, None] = None
        self._original_title: Union[str, None] = None
        self._overview: Union[str, None] = None
        self._episode_title: Union[str, None] = None
        self._season: Union[int, None] = None
        self._episode: Union[int, None] = None
        self._original_language: Union[str, None] = None
        self._media_type: Union[str, None] = None
        self._year: Union[int, None] = None
        self._tagline: Union[str, None] = None
        self._used_guessit: Union[bool, None] = None
        self._used_tmdb: Union[bool, None] = None
        self._used_openai: Union[bool, None] = None
        self._created_at: Union[datetime, None] = None
        self._modified_at: Union[datetime, None] = None

    def reset(self):
        self.__init__()
        return self

    def with_id(self, record_id: uuid4):
        self._id = record_id
        return self

    def with_searchable_reference(self, searchable_reference: str):
        if searchable_reference is None or searchable_reference.strip() == '':
            return self


        self._searchable_reference = create_searchable_reference(searchable_reference)
        return self

    def with_tmdb_id(self, tmdb_id: int):
        self._tmdb_id = tmdb_id
        return self

    def with_tmdb_series_id(self, tmdb_series_id: int):
        self._tmdb_series_id = tmdb_series_id
        return self

    def with_imdb_id(self, imdb_id: str):
        self._imdb_id = imdb_id
        return self

    def with_tvdb_id(self, tvdb_id: int):
        self._tvdb_id = tvdb_id
        return self

    def with_tvrage_id(self, tvrage_id: int):
        self._tvrage_id = tvrage_id
        return self

    def with_wikidata_id(self, wikidata_id: str):
        self._wikidata_id = wikidata_id
        return self

    def with_facebook_id(self, facebook_id: str):
        self._facebook_id = facebook_id
        return self

    def with_instagram_id(self, instagram_id: str):
        self._instagram_id = instagram_id
        return self

    def with_twitter_id(self, twitter_id: str):
        self._twitter_id = twitter_id
        return self

    def with_genres(self, genres: list):
        if not genres:
            self._genres = None
            return self

        genres_dict = {
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
            10768: "War & Politics"
        }

        parsed_genres = set()

        if not isinstance(genres, list):
            return self

        for genre in genres:
            if isinstance(genre, dict):
                if 'name' not in genre:
                    continue

                parsed_genres.add(genre.get('name'))
            elif isinstance(genre, int):
                if genre not in genres_dict:
                    continue
                parsed_genres.add(genres_dict[genre])

        self._genres =  list(parsed_genres)

        return self

    def with_title(self, title: str):
        self._title = title
        return self

    def with_original_title(self, original_title: str):
        self._original_title = original_title
        return self

    def with_overview(self, overview: str):
        self._overview = overview
        return self

    def with_episode_title(self, episode_title: str):
        self._episode_title = episode_title
        return self

    def with_season(self, season: int):
        self._season = season
        return self

    def with_episode(self, episode: int):
        self._episode = episode
        return self

    def with_original_language(self, original_language: str):
        self._original_language = original_language
        return self

    def with_media_type(self, media_type: str):
        normalized = normalize_media_type(media_type)
        self._media_type = normalized if normalized else "unknown"

        return self

    def with_year(self, year: int):
        self._year = year
        return self

    def with_tagline(self, tagline: str):
        self._tagline = tagline
        return self

    def with_used_guessit(self, used_guessit: bool):
        self._used_guessit = used_guessit
        return self

    def with_used_tmdb(self, used_tmdb: bool):
        self._used_tmdb = used_tmdb
        return self

    def with_used_openai(self, used_openai: bool):
        self._used_openai = used_openai
        return self

    def with_created_at(self, created_at: datetime):
        self._created_at = created_at
        return self

    def with_modified_at(self, modified_at: datetime):
        self._modified_at = modified_at
        return self

    def build(self) -> dict:
        return {
            'id': self._id,
            'searchable_reference': self._searchable_reference,
            'tmdb_id': self._tmdb_id,
            'imdb_id': self._imdb_id,
            'tmdb_series_id': self._tmdb_series_id,
            'tvdb_id': self._tvdb_id,
            'tvrage_id': self._tvrage_id,
            'wikidata_id': self._wikidata_id,
            'facebook_id': self._facebook_id,
            'instagram_id': self._instagram_id,
            'twitter_id': self._twitter_id,
            'genres': self._genres,
            'title': self._title,
            'original_title': self._original_title,
            'overview': self._overview,
            'episode_title': self._episode_title,
            'season': self._season,
            'episode': self._episode,
            'original_language': self._original_language,
            'media_type': self._media_type,
            'year': self._year,
            'tagline': self._tagline,
            'used_guessit': self._used_guessit,
            'used_tmdb': self._used_tmdb,
            'used_openai': self._used_openai,
            'created_at': self._created_at,
            'modified_at': self._modified_at
        }

def merge_media_info(existing: dict, new: dict) -> Optional[dict]:
    if existing is None and new is None:
        return None

    if existing is None and new is not None:
        return new.copy()

    merged = existing.copy()

    if new is None:
        return merged

    for key, value in new.items():
        if value is None:
            continue

        if key in ['used_guessit', 'used_tmdb', 'used_openai'] and key in merged and merged[key] is True:
            # If we already said we used a service, we won't override it.
            continue

        merged[key] = value
    return merged

def is_media_type_valid(media_type: str) -> bool:
    normalized = normalize_media_type(media_type)
    return normalized is not None
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Optional

from src.converters.create_searchable_reference import create_searchable_reference
from src.models.media_info import MediaInfoBuilder


class RequestMode(str, Enum):
    FILENAME = "filename"
    METADATA = "metadata"


def _normalize_media_type(media_type: Optional[str]) -> Optional[str]:
    if media_type is None:
        return None

    builder = MediaInfoBuilder().with_media_type(media_type)
    return builder.build().get("media_type")


@dataclass
class MediaIdentificationRequest:
    mode: RequestMode
    file_path: Optional[str] = None
    media_type: Optional[str] = None
    title: Optional[str] = None
    year: Optional[int] = None
    season: Optional[int] = None
    episode: Optional[int] = None
    tmdb_id: Optional[int] = None
    tmdb_series_id: Optional[int] = None
    imdb_id: Optional[str] = None
    extra: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.media_type = _normalize_media_type(self.media_type)
        self._validate()

    @classmethod
    def from_filename(cls, file_path: str) -> "MediaIdentificationRequest":
        if file_path is None or file_path.strip() == "":
            raise ValueError("file_path must be provided for filename requests.")

        return cls(mode=RequestMode.FILENAME, file_path=file_path.strip())

    @classmethod
    def from_metadata(
        cls,
        *,
        media_type: str,
        title: str,
        year: int,
        season: Optional[int] = None,
        episode: Optional[int] = None,
        tmdb_id: Optional[int] = None,
        tmdb_series_id: Optional[int] = None,
        imdb_id: Optional[str] = None,
        extra: Optional[Dict[str, Any]] = None,
    ) -> "MediaIdentificationRequest":
        return cls(
            mode=RequestMode.METADATA,
            media_type=media_type,
            title=title,
            year=year,
            season=season,
            episode=episode,
            tmdb_id=tmdb_id,
            tmdb_series_id=tmdb_series_id,
            imdb_id=imdb_id,
            extra=extra or {},
        )

    @property
    def is_filename_mode(self) -> bool:
        return self.mode == RequestMode.FILENAME

    @property
    def is_metadata_mode(self) -> bool:
        return self.mode == RequestMode.METADATA

    @property
    def has_file_path(self) -> bool:
        return bool(self.file_path and self.file_path.strip())

    def seed_media_info(self) -> Dict[str, Any]:
        builder = MediaInfoBuilder()

        if self.title:
            builder = (
                builder.with_title(self.title.strip())
                .with_original_title(self.title.strip())
                .with_searchable_reference(self.title)
            )

        if self.media_type:
            builder = builder.with_media_type(self.media_type)

        if self.year is not None:
            builder = builder.with_year(self.year)

        if self.season is not None:
            builder = builder.with_season(self.season)

        if self.episode is not None:
            builder = builder.with_episode(self.episode)

        if self.tmdb_id is not None:
            builder = builder.with_tmdb_id(self.tmdb_id)

        if self.tmdb_series_id is not None:
            builder = builder.with_tmdb_series_id(self.tmdb_series_id)

        if self.imdb_id is not None:
            builder = builder.with_imdb_id(self.imdb_id)

        builder = builder.with_used_guessit(False).with_used_openai(False)

        return builder.build()

    def to_logging_payload(self) -> Dict[str, Any]:
        payload = {
            "mode": self.mode.value,
            "media_type": self.media_type,
            "title": self.title,
            "year": self.year,
            "season": self.season,
            "episode": self.episode,
            "has_file_path": self.has_file_path,
        }
        if self.tmdb_id is not None:
            payload["tmdb_id"] = self.tmdb_id
        if self.tmdb_series_id is not None:
            payload["tmdb_series_id"] = self.tmdb_series_id
        if self.imdb_id is not None:
            payload["imdb_id"] = self.imdb_id
        payload.update(self.extra)
        return payload

    def _validate(self) -> None:
        if self.mode == RequestMode.FILENAME:
            if not self.has_file_path:
                raise ValueError("file_path must be provided for filename requests.")
            return

        if self.media_type is None:
            raise ValueError("media_type must be provided for metadata requests.")

        if self.title is None or self.title.strip() == "":
            raise ValueError("title must be provided for metadata requests.")

        if self.year is None:
            raise ValueError("year must be provided for metadata requests.")

        if self.media_type == "tv":
            if self.season is None or self.episode is None:
                raise ValueError("season and episode must be provided for TV metadata requests.")

    def derive_searchable_reference(self) -> Optional[str]:
        if self.title is None:
            return None
        return create_searchable_reference(self.title)



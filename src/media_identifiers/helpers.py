"""Media record helpers: filling a record builder from the basic identification fields."""

from src.models.media_info import MediaInfoBuilder
from src.utils import get_otel_log_handler

_logger = get_otel_log_handler("MediaIdentifierHelpers")


@_logger.trace("apply_basic_media_attributes")
def apply_basic_media_attributes(
    builder: MediaInfoBuilder,
    *,
    title: str | None,
    media_type: str | None,
    year: int | None,
    season: int | None = None,
    episode: int | None = None,
    searchable_reference: str | None = None,
) -> MediaInfoBuilder:
    """Copy the basic identification fields into a builder, skipping empty values.

    The stripped title is used as both title and original title, and as the search key when no
    ``searchable_reference`` is given.

    Returns:
        The same builder.
    """
    if title:
        normalized_title = title.strip()
        if normalized_title:
            builder = builder.with_title(normalized_title).with_original_title(normalized_title)
            searchable_reference = searchable_reference or normalized_title

    if searchable_reference:
        builder = builder.with_searchable_reference(searchable_reference)

    if media_type is not None:
        builder = builder.with_media_type(media_type)

    if year is not None:
        builder = builder.with_year(year)

    if season is not None:
        builder = builder.with_season(season)

    if episode is not None:
        builder = builder.with_episode(episode)

    return builder

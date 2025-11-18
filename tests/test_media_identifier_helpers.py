from src.media_identifiers.helpers import (
    apply_basic_media_attributes,
    parse_season_episode_string,
)
from src.models.media_info import MediaInfoBuilder


def test_apply_basic_media_attributes_sets_core_fields():
    builder = apply_basic_media_attributes(
        MediaInfoBuilder(),
        title="Example Title",
        media_type="movie",
        year=2024,
        season=2,
        episode=5,
    )

    data = builder.build()

    assert data["title"] == "Example Title"
    assert data["original_title"] == "Example Title"
    assert data["searchable_reference"] is not None
    assert data["media_type"] == "movie"
    assert data["year"] == 2024
    assert data["season"] == 2
    assert data["episode"] == 5


def test_parse_season_episode_string_valid_value():
    season, episode = parse_season_episode_string("Season: 3, Episode: 10")
    assert season == 3
    assert episode == 10


def test_parse_season_episode_string_invalid_value():
    season, episode = parse_season_episode_string("invalid-format")
    assert season is None
    assert episode is None


from src.media_identifiers.helpers import apply_basic_media_attributes
from src.models.media_info import MediaInfoBuilder


def test_apply_basic_media_attributes_sets_core_fields() -> None:
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

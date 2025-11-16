import pytest

from src.models.media_identification_request import MediaIdentificationRequest, RequestMode


def test_from_filename_requires_value():
    with pytest.raises(ValueError):
        MediaIdentificationRequest.from_filename("")


def test_from_filename_mode():
    request = MediaIdentificationRequest.from_filename("Some.Show.S01E01.mkv")
    assert request.mode == RequestMode.FILENAME
    assert request.file_path == "Some.Show.S01E01.mkv"
    assert request.has_file_path is True


def test_metadata_requires_tv_episode():
    with pytest.raises(ValueError):
        MediaIdentificationRequest.from_metadata(
            media_type="tv",
            title="Example Show",
            year=2024,
            season=None,
            episode=1,
        )


def test_metadata_normalizes_media_type():
    request = MediaIdentificationRequest.from_metadata(
        media_type="TV Show",
        title="Example Show",
        year=2024,
        season=1,
        episode=2,
    )

    assert request.media_type == "tv"
    assert request.seed_media_info()["media_type"] == "tv"



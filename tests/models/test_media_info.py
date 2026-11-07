from src.models.media_info import MediaInfoBuilder, merge_media_info


def test_merge_media_info_ignores_none_values() -> None:
    merged = merge_media_info({"title": "Slow Horses", "year": 2022}, {"title": None, "year": 2026})

    assert merged == {"title": "Slow Horses", "year": 2026}


def test_merge_media_info_keeps_service_flags_that_are_already_true() -> None:
    merged = merge_media_info({"used_guessit": True}, {"used_guessit": False})

    assert merged == {"used_guessit": True}


def test_merge_media_info_without_existing_copies_the_new_record() -> None:
    new = {"title": "Fargo"}

    merged = merge_media_info(None, new)

    assert merged == new
    assert merged is not new


def test_with_genres_maps_tmdb_ids_and_named_genres() -> None:
    media = MediaInfoBuilder().with_genres([18, 99999, {"name": "Thriller"}, {"id": 1}]).build()

    assert sorted(media["genres"]) == ["Drama", "Thriller"]


def test_with_media_type_unrecognized_value_becomes_unknown() -> None:
    assert MediaInfoBuilder().with_media_type("podcast").build()["media_type"] == "unknown"

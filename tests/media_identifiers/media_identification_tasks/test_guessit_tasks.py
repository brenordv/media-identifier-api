import pytest
from guessit.api import GuessitException

from src.media_identifiers.media_identification_tasks import guessit_tasks
from src.media_identifiers.media_identification_tasks.guessit_tasks import (
    _build_fallback_input,
    identify_media_with_guess_it,
)

SLOW_HORSES_FILE = "/watch/Slow.Horses.S06E06.Judgment.Day.1080p.ATVP.WEB-DL.DDP5.1.H.264-NTb.mkv"


def test_build_fallback_input_limits_noisy_path_segments() -> None:
    parts = [
        "mnt",
        "skystorage",
        "apps",
        "transmission-vpn",
        "data",
        "completed",
        "Pulse.2.Afterlife.2008.1080p.BluRay.x264-GUACAMOLE",
        "gua-pulse2.2008-1080p.srr",
    ]

    fallback = _build_fallback_input(parts)
    fallback_lower = fallback.lower()

    assert "skystorage" not in fallback_lower
    assert "apps" not in fallback_lower
    assert "completed" not in fallback_lower
    assert "data" not in fallback_lower
    assert "transmission" not in fallback_lower
    assert "pulse" in fallback_lower
    assert "afterlife" in fallback_lower


def test_build_fallback_input_skips_data_folder() -> None:
    parts = [
        "mnt",
        "skystorage",
        "apps",
        "transmission-vpn",
        "data",
        "completed",
        "It.Chapter.One.2017.UHD.BluRay.1080p.DD+Atmos.5.1.DoVi.HDR10.x265-SM737",
        "screens.png",
    ]

    fallback = _build_fallback_input(parts)
    fallback_lower = fallback.lower()

    assert "data" not in fallback_lower
    assert "it" in fallback_lower
    assert "chapter" in fallback_lower
    assert "one" in fallback_lower


def test_build_fallback_input_skips_proof_image_segment() -> None:
    parts = [
        "mnt",
        "skystorage",
        "apps",
        "transmission-vpn",
        "data",
        "completed",
        "Pulse.3.2008.1080p.BluRay.x264-GUACAMOLE",
        "Proof",
        "gua-pulse3.2008-1080p-proof.jpg",
    ]

    fallback = _build_fallback_input(parts)
    fallback_lower = fallback.lower()

    assert "proof" not in fallback_lower
    assert "pulse.3.2008" in fallback_lower


def test_build_fallback_input_prefers_release_folder_over_file() -> None:
    parts = [
        "mnt",
        "skystorage",
        "apps",
        "transmission-vpn",
        "data",
        "completed",
        "Pulse.3.2008.1080p.BluRay.x264-GUACAMOLE",
        "gua-pulse3.2008-1080p.mkv",
    ]

    fallback = _build_fallback_input(parts)
    fallback_lower = fallback.lower()

    assert "pulse.3.2008" in fallback_lower
    assert "pulse3" not in fallback_lower


@pytest.mark.parametrize("file_path", [SLOW_HORSES_FILE, SLOW_HORSES_FILE.lower()])
def test_identify_media_with_guess_it_reads_series_season_and_episode(file_path: str) -> None:
    media = identify_media_with_guess_it(file_path)

    assert media is not None
    assert media["title"].lower() == "slow horses"
    assert media["media_type"] == "tv"
    assert (media["season"], media["episode"]) == (6, 6)
    assert media["used_guessit"] is True


def test_identify_media_with_guess_it_guessit_failure_returns_none(monkeypatch: pytest.MonkeyPatch) -> None:
    def failing_guessit(candidate: str) -> dict[str, object]:
        raise GuessitException(candidate, {})

    monkeypatch.setattr(guessit_tasks, "guessit", failing_guessit)

    assert identify_media_with_guess_it(SLOW_HORSES_FILE) is None

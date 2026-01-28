from src.media_identifiers.media_identification_tasks.guessit_tasks import _build_fallback_input


def test_build_fallback_input_limits_noisy_path_segments():
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


def test_build_fallback_input_skips_data_folder():
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

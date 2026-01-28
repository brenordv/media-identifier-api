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
    assert "pulse" in fallback_lower
    assert "afterlife" in fallback_lower

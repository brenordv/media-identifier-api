"""Live end-to-end checks against TMDB, OpenAI and the configured Postgres database.

Run with ``MEDIA_IDENTIFIER_RUN_INTEGRATION=1 uv run pytest -m integration``; the database settings come from `.env`.
These tests write to the database.
"""

import os
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.integration

if os.environ.get("MEDIA_IDENTIFIER_RUN_INTEGRATION") != "1":
    pytest.skip("Set MEDIA_IDENTIFIER_RUN_INTEGRATION=1 to run the integration suite.", allow_module_level=True)


@pytest.fixture(scope="module")
def client() -> Iterator[TestClient]:
    from main import app

    with TestClient(app) as test_client:
        yield test_client


@pytest.mark.parametrize(
    "query",
    [
        "Shin Godzilla (2016) 1080p Hybrid Bluray REMUX AVC Dual DTS-HD MA 3.1",
        "The Blob (1988) (1080p BluRay x265 10bit Tigole).mkv",
        "The Blob (1988) (1080p BluRay x265 10bit Tigole)/movie.mkv",
        "Rick.and.Morty.S07E10.Fear.No.Mort.1080p.HMAX.WEB-DL.DDP5.1.H.264-FLUX-poster.jpg",
        "Rick.and.Morty.S07E10.Fear.No.Mort.1080p.HMAX.WEB-DL.DDP5.1.H.264-FLUX/poster.jpg",
        "rick.and.morty.s07e10.fear.no.mort.1080p.hmax.web-dl.ddp5.1.h.264-flux/poster.jpg",
        "tmp/Death.Proof.2007.1080p.BluRay.x264-1920/1920-proof.rar",
        "Fargo.1080p.BluRay.x264-1920/1920-proof.rmkv",
        "Fargo.1996.1080p.BluRay.x264-1920/1920-fargo.rmkv",
        "Fargo.S01E01.1080p.BluRay.x264-1920/1920-fargo.rmkv",
        "tmp/Killing.Zoe.1993.1080p.BluRay.x264-LCHD/lchd-kz1080p.rar",
        "Slow.Horses.S02.NORDiC.720p.WEB-DL.H.265.DD5.1-CiNEMiX/Slow.Horses.S02E05.NORDiC.720p.WEB-DL.H.265.DD5.1-CiNEMiX-poster.jpg",
        "/mnt/mock-test-files/Slow.Horses.S03.NORDiC.720p.WEB-DL.H.265.DD5.1-CiNEMiX/Slow.Horses.S03E01.NORDiC.720p.WEB-DL.H.265.DD5.1-CiNEMiX.nfo",
        "/mnt/mock-test-files/American.Dad.S20E01.1080p.WEBRip.x264-BAE/American.Dad.S20E01.1080p.WEBRip.x264-BAE.mkv",
        "/mnt/mock-test-files/Final.Destination.MOViE.PACK.1080p.BluRay.x264-HiTSQUAD/The.Final.Destination.1080p.BluRay.x264-METiS/m-fd4-1080p.mkv",
        "/mnt/mock-test-files/Marvel.Cinematic.Universe.Phase.01-04.1080p.BluRay.10Bit.X265.DD.5.1-Chivaman/The.Incredible.Hulk.2008.1080p.BluRay.10Bit.X265.DD.5.1-Chivaman.mkv",
        "/watch/Stake.Land.II.2016.1080p.BluRay.x264-PSYCHD/Subs/Stake.Land.II.2016.1080p.BluRay.x264-PSYCHD.idx",
    ],
)
def test_guess_endpoint_identification(client: TestClient, query: str) -> None:
    response = client.get("/api/guess", params={"it": query})

    assert response.status_code in (200, 204)


def test_media_info_endpoint_movie_metadata(client: TestClient) -> None:
    response = client.get("/api/media-info", params={"title": "Possessed", "year": 2000, "media_type": "movie"})

    assert response.status_code in (200, 204)

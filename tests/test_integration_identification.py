import os

import httpx
import pytest
from dotenv import load_dotenv

load_dotenv()

REQUIRED_ENV_VARS = [
    "TMDB_API_KEY",
    "OPENAI_API_KEY",
]

_missing_env = [env for env in REQUIRED_ENV_VARS if not os.environ.get(env)]
if _missing_env:
    pytest.skip(
        f"Skipping integration tests: missing environment variables {_missing_env}",
        allow_module_level=True,
    )

from main import app


@pytest.fixture(scope="module")
def anyio_backend():
    return "asyncio"


@pytest.fixture(scope="module")
async def async_client():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client


@pytest.mark.anyio
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
async def test_guess_endpoint_identification(async_client: httpx.AsyncClient, query: str):
    response = await async_client.get("/api/guess", params={"it": query})
    assert response.status_code in (200, 204)


@pytest.mark.anyio
async def test_media_info_endpoint_movie_metadata(async_client: httpx.AsyncClient):
    response = await async_client.get(
        "/api/media-info",
        params={
            "title": "Possessed",
            "year": 2000,
            "media_type": "movie",
        },
    )

    assert response.status_code in (200, 204)


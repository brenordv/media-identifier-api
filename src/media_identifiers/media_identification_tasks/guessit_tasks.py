import re
from typing import List, Optional, Tuple

from guessit import guessit

from src.media_identifiers.helpers import apply_basic_media_attributes
from src.models.media_info import MediaInfoBuilder
from src.utils import get_otel_log_handler

_logger = get_otel_log_handler("MediaIdentifier")

_PATH_SEGMENT_FILTER = {
    "tmp",
    "watch",
    "mnt",
    "mock-test-files",
    "data",
    "apps",
    "skystorage",
    "transmission-vpn",
}
_SEGMENT_NOISE_TOKENS = {
    "proof",
    "poster",
    "posters",
    "sample",
    "samples",
    "subs",
    "subtitle",
    "subtitles",
    "nfo",
    "info",
    "readme",
    "extras",
    "extra",
    "bonus",
    "screen",
    "screens",
    "screenshot",
    "screenshots",
    "cover",
    "covers",
    "completed",
    "complete",
    "downloads",
    "download",
    "incoming",
    "incomplete",
}
_EXTENSION_TOKENS = {
    "mkv",
    "mp4",
    "avi",
    "mov",
    "wmv",
    "flv",
    "ts",
    "m2ts",
    "rmkv",
    "rar",
    "zip",
    "7z",
    "r00",
    "r01",
    "r02",
    "sfv",
    "md5",
    "srr",
    "idx",
    "srt",
    "sub",
    "sup",
    "nfo",
    "txt",
    "jpg",
    "jpeg",
    "png",
    "gif",
    "bmp",
    "webp",
    "mp3",
    "flac",
    "wav",
    "ogg",
    "m4a",
}
_IMAGE_EXTENSIONS = {"jpg", "jpeg", "png", "gif", "bmp", "webp"}
_VISUAL_ASSET_TOKENS = {
    "art",
    "artwork",
    "cover",
    "covers",
    "poster",
    "posters",
    "proof",
    "sample",
    "samples",
    "screen",
    "screens",
    "screenshot",
    "screenshots",
}
_GENERIC_TITLE_TOKENS = {
    "the",
    "and",
    "or",
    "a",
    "an",
    "movie",
    "pack",
    "collection",
    "anthology",
    "phase",
    "cinematic",
    "universe",
    "complete",
    "edition",
    "cut",
    "version",
    "remastered",
    "extended",
    "imax",
    "uhd",
    "hdr",
    "remux",
    "web",
    "webdl",
    "webrip",
    "bluray",
    "bdrip",
    "hdrip",
    "brip",
    "dvdrip",
    "dvdr",
    "digital",
    "rip",
    "x264",
    "x265",
    "h264",
    "h265",
    "hevc",
    "ddp",
    "dd",
    "dts",
    "atmos",
    "ac3",
    "aac",
    "truehd",
    "proper",
    "repack",
    "rerip",
    "subs",
    "subtitles",
    "dub",
    "multi",
    "1080p",
    "720p",
    "2160p",
    "4k",
    "10bit",
    "hdr10",
    "hdr10plus",
    "dolby",
    "vision",
}
_SOURCE_NOISE_TOKENS = (
    set(_GENERIC_TITLE_TOKENS)
    | _SEGMENT_NOISE_TOKENS
    | _EXTENSION_TOKENS
    | {"tmp", "watch", "mnt", "mock", "files", "file", "disc", "disk", "part"}
)
_LOW_INFORMATION_EXTENSIONS = {"rar", "zip", "7z", "r00", "r01", "r02", "sfv", "md5", "srr", "txt"}
_MAX_FALLBACK_SEGMENTS = 2
_VALID_MEDIA_TYPES = {"movie", "episode", "tv"}
_TOKEN_SPLIT_RE = re.compile(r"[^\w]+")
_TRAILING_YEAR_PATTERN = re.compile(
    r"^(?P<title>.*?)(?:[\s\[\(\-]+(?P<year>(?:18|19|20)\d{2}))[\]\)\s]*$",
    re.IGNORECASE,
)


@_logger.trace("identify_media_with_guess_it")
def identify_media_with_guess_it(file_path: str) -> Optional[dict]:
    try:
        _logger.debug(f"Identifying media file: {file_path}")

        best_metadata: Optional[dict] = None
        best_score = float("-inf")

        for index, candidate in enumerate(_generate_guessit_inputs(file_path)):
            raw_metadata = guessit(candidate)
            normalized_metadata = _normalize_guessit_metadata(dict(raw_metadata))
            quality = _metadata_quality(normalized_metadata)

            if quality == float("-inf"):
                continue

            noise_penalty = _candidate_noise_penalty(candidate)
            score = quality - noise_penalty + max(0, 3 - index)

            if score > best_score:
                best_score = score
                best_metadata = normalized_metadata

        if best_metadata is None:
            return None

        return _create_record_from_guessit_data(best_metadata)
    except Exception as exc:  # noqa: BLE001
        _logger.error(f"Error identifying media file {file_path}: {exc}")
        return None


def _create_record_from_guessit_data(guess_it_data):
    title = guess_it_data.get("title")
    builder = apply_basic_media_attributes(
        MediaInfoBuilder(),
        title=title,
        media_type=guess_it_data.get("type"),
        year=guess_it_data.get("year"),
        season=guess_it_data.get("season"),
        episode=guess_it_data.get("episode"),
        searchable_reference=title,
    )

    return (
        builder.with_episode_title(guess_it_data.get("episode_title"))
        .with_original_language(guess_it_data.get("original_language"))
        .with_used_guessit(True)
        .build()
    )


def _generate_guessit_inputs(file_path: str) -> List[str]:
    parts = [part for part in re.split(r"[\\/]", file_path) if part]

    cleaned_parts = [part for part in parts if part.lower() not in _PATH_SEGMENT_FILTER]
    if not cleaned_parts:
        cleaned_parts = parts

    candidates: List[str] = []
    seen: set[str] = set()

    def build_candidates(skip_visual_assets: bool) -> None:
        for index, segment in enumerate(reversed(cleaned_parts)):
            normalized_segment = _normalize_segment(segment)
            if not normalized_segment:
                continue

            if skip_visual_assets and _segment_is_visual_asset(normalized_segment):
                continue

            if _segment_is_weak_file_candidate(normalized_segment, cleaned_parts, index):
                continue

            if not _segment_has_meaningful_tokens(normalized_segment):
                continue

            if normalized_segment not in seen:
                candidates.append(normalized_segment)
                seen.add(normalized_segment)

    build_candidates(skip_visual_assets=True)
    if not candidates:
        build_candidates(skip_visual_assets=False)

    fallback = _build_fallback_input(cleaned_parts)
    if fallback and fallback not in seen:
        candidates.append(fallback)

    if not candidates and fallback:
        candidates.append(fallback)

    return candidates


def _normalize_segment(segment: str) -> str:
    normalized = segment.strip()
    if not normalized:
        return ""

    normalized = normalized.replace("_", " ")
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized


def _segment_has_meaningful_tokens(segment: str) -> bool:
    base, extension = _split_basename_and_extension(segment)
    tokens = _tokenize(base)
    meaningful_tokens = [token for token in tokens if _is_meaningful_segment_token(token)]

    if extension:
        if extension in _LOW_INFORMATION_EXTENSIONS:
            return len(meaningful_tokens) >= 2
        return len(meaningful_tokens) >= 1

    return len(meaningful_tokens) >= 1


def _split_basename_and_extension(segment: str) -> Tuple[str, Optional[str]]:
    if "." not in segment:
        return segment, None

    base, extension = segment.rsplit(".", 1)
    extension_lower = extension.lower()
    if extension_lower in _EXTENSION_TOKENS:
        return base, extension_lower

    return segment, None


def _is_meaningful_segment_token(token: str) -> bool:
    lower_token = token.lower()

    if lower_token in _SEGMENT_NOISE_TOKENS or lower_token in _EXTENSION_TOKENS:
        return False

    if lower_token.isdigit():
        return False

    letters = [char for char in token if char.isalpha()]
    if len(letters) < 2:
        return False

    if any(char.isdigit() for char in token) and len(letters) < 3:
        return False

    return True


def _build_fallback_input(parts: List[str]) -> str:
    if not parts:
        return ""

    meaningful_parts = []
    last_meaningful_count = 0
    for part in parts:
        normalized_part = _normalize_segment(part)
        if not normalized_part:
            continue
        if _segment_is_visual_asset(normalized_part):
            continue
        if _segment_is_weak_file_segment(normalized_part, last_meaningful_count):
            continue
        if _segment_has_meaningful_tokens(normalized_part):
            meaningful_parts.append(normalized_part)
            last_meaningful_count = _count_meaningful_tokens(normalized_part)

    candidate_parts = meaningful_parts[-_MAX_FALLBACK_SEGMENTS:] if meaningful_parts else parts[-_MAX_FALLBACK_SEGMENTS:]
    normalized_parts = [part.replace("_", " ") for part in candidate_parts if part]
    normalized = " ".join(normalized_parts)
    normalized = normalized.replace("-", " ")
    normalized = re.sub(r"\s+", " ", normalized)

    return normalized.strip()


def _segment_is_visual_asset(segment: str) -> bool:
    base, extension = _split_basename_and_extension(segment)
    if not extension or extension not in _IMAGE_EXTENSIONS:
        return False

    tokens = _tokenize(base)
    return any(token.lower() in _VISUAL_ASSET_TOKENS for token in tokens)


def _segment_is_weak_file_candidate(segment: str, parts: List[str], reversed_index: int) -> bool:
    if not _segment_has_media_extension(segment):
        return False

    parent_index = len(parts) - 2 - reversed_index
    if parent_index < 0:
        return False

    parent_segment = _normalize_segment(parts[parent_index])
    if not parent_segment:
        return False

    file_tokens = _count_meaningful_tokens(segment)
    parent_tokens = _count_meaningful_tokens(parent_segment)
    if parent_tokens == 0:
        return False

    return file_tokens < parent_tokens


def _segment_is_weak_file_segment(segment: str, previous_meaningful_count: int) -> bool:
    if not _segment_has_media_extension(segment):
        return False

    file_tokens = _count_meaningful_tokens(segment)
    if previous_meaningful_count == 0:
        return False

    return file_tokens < previous_meaningful_count


def _segment_has_media_extension(segment: str) -> bool:
    _, extension = _split_basename_and_extension(segment)
    return extension in _EXTENSION_TOKENS if extension else False


def _count_meaningful_tokens(segment: str) -> int:
    base, _ = _split_basename_and_extension(segment)
    tokens = _tokenize(base)
    return sum(1 for token in tokens if _is_meaningful_segment_token(token))


def _normalize_guessit_metadata(metadata: dict) -> dict:
    normalized = dict(metadata)

    normalized["season"] = _coerce_int(normalized.get("season"))
    normalized["episode"] = _coerce_int(normalized.get("episode"))
    normalized["year"] = _coerce_int(normalized.get("year"))

    title = normalized.get("title")
    if isinstance(title, str):
        clean_title, trailing_year = _strip_trailing_year(title)
        normalized["title"] = clean_title

        if trailing_year is not None:
            normalized["year"] = trailing_year

    year = normalized.get("year")
    if isinstance(year, int) and not _is_plausible_year(year):
        normalized.pop("year", None)

    return normalized


def _metadata_quality(metadata: dict) -> float:
    title = metadata.get("title")
    if not title:
        return float("-inf")

    tokens = _tokenize(title)
    meaningful_tokens = [token for token in tokens if _token_is_meaningful_title_token(token)]

    if not meaningful_tokens:
        return float("-inf")

    score = len(meaningful_tokens) * 10
    extension_hits = sum(1 for token in tokens if token.lower() in _EXTENSION_TOKENS)
    score -= extension_hits * 10

    media_type = metadata.get("type")
    if isinstance(media_type, str) and media_type.lower() in _VALID_MEDIA_TYPES:
        score += 3

    if metadata.get("season") is not None:
        score += 1

    if metadata.get("episode") is not None:
        score += 1

    year = metadata.get("year")
    if isinstance(year, int):
        if _is_plausible_year(year):
            score += 2
        else:
            score -= 4

    return score


def _candidate_noise_penalty(candidate: str) -> float:
    penalty = 0.0
    for token in _tokenize(candidate):
        lower_token = token.lower()
        if lower_token in _SOURCE_NOISE_TOKENS:
            penalty += 1.0
        elif lower_token.isdigit():
            penalty += 0.5

    return penalty


def _token_is_meaningful_title_token(token: str) -> bool:
    lower_token = token.lower()

    if lower_token in _GENERIC_TITLE_TOKENS or lower_token in _EXTENSION_TOKENS:
        return False

    letters = [char for char in token if char.isalpha()]
    if len(letters) < 2:
        return False

    if any(char.isdigit() for char in token) and len(letters) < 3:
        return False

    return True


def _strip_trailing_year(title: str) -> Tuple[str, Optional[int]]:
    stripped = title.strip()
    match = _TRAILING_YEAR_PATTERN.match(stripped)
    if not match:
        return stripped, None

    cleaned_title = match.group("title").strip(" -_.([")
    cleaned_title = re.sub(r"\s{2,}", " ", cleaned_title).strip()

    year_value = match.group("year")
    year = int(year_value) if year_value and year_value.isdigit() else None

    return cleaned_title, year


def _coerce_int(value) -> Optional[int]:  # noqa: ANN001
    if isinstance(value, int):
        return value

    if isinstance(value, str) and value.isdigit():
        return int(value)

    if isinstance(value, list):
        for item in value:
            coerced = _coerce_int(item)
            if coerced is not None:
                return coerced

    return None


def _is_plausible_year(year: int) -> bool:
    return 1888 <= year <= 2100


def _tokenize(text: str) -> List[str]:
    return [token for token in _TOKEN_SPLIT_RE.split(text) if token]

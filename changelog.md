# Changelog

All notable changes to this project are documented in this file. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses [Semantic Versioning](https://semver.org/).

## [2.0.0] - 2026-11-06

### Breaking changes

- Python 3.14 or newer is required, the version the Docker image runs.
- Dependencies are managed with [uv](https://docs.astral.sh/uv/): `pyproject.toml` and `uv.lock` replace
  `requirements.txt`. Install with `uv sync` and start with `uv run python main.py`.
- The Docker image no longer contains `.env`. Pass the settings when the container starts (`run-image.sh` uses
  `--env-file .env`; see `.env.example`).
- The image runs `uvicorn --workers $WORKERS` instead of gunicorn with the deprecated `uvicorn.workers` worker.
- On TV results, `tmdb_id` is the TMDB id of the episode; the series id is in `tmdb_series_id`. Movies are unchanged.
- The database schema changes on first start (see Migrations below). A 1.x deployment that shares the database
  afterwards gets HTTP 500 when it tries to cache a new TV episode, because the new CHECK constraint rejects the
  series-keyed rows 1.x writes.
- Failed requests return a generic `500` message, and `request_history.error_message` stores only that message plus
  the exception class. Details are in the logs.
- `/api/statistics` accepts `num_requests` from 1 to 1000; `it` and `title` accept up to 1024 characters.
- `/api/media-info` accepts `season` from 0 (specials) to 9999 and `episode` from 1 to 9999; values outside those
  ranges get `422`.

### Added

- Versioned SQL migrations in `migrations/`, applied once each in order at startup and by
  `uv run python -m src.database.migrate`, recorded in a `schema_migrations` table with checksums, and serialized
  with a PostgreSQL advisory lock. A fresh install only needs an empty database. A run stops without changes when
  an applied file was edited or a pending file is numbered below one already applied.
- Migrations:
  - `0001_baseline`: the 1.x tables and indexes (a no-op on existing databases).
  - `0002_cache_identity_per_media_type`: `UNIQUE (tmdb_id)` becomes `UNIQUE (tmdb_id, media_type)`.
  - `0003_remove_tv_rows_keyed_by_series_id`: deletes TV rows whose `tmdb_id` is their series id and adds a CHECK
    constraint that keeps them out. Those episodes are identified again on their next request.
- `.env.example` with every setting.
- Hermetic unit test suite (no database, TMDB, OpenAI or telemetry collector needed) and an opt-in integration
  suite: `MEDIA_IDENTIFIER_RUN_INTEGRATION=1 uv run pytest -m integration`.
- ruff, ruff format and mypy configuration.

### Changed

- Dependencies updated: guessit 4.4.0, fastapi 0.162.0, uvicorn 0.54.0, openai 3.46.0, requests 2.34.2,
  python-dotenv 1.2.4, simple-log-factory-ext-otel 2.0.0. psycopg2 is replaced by raccoontools-db 1.1.0
  (psycopg 3 connection pool).
- Endpoints that call TMDB, OpenAI or the database run in FastAPI's threadpool, so a slow identification no longer
  blocks other requests or the health check.
- The database pool is opened and closed by the application lifespan; repositories are injected into the endpoints.
- Cache title matching is an exact, case-insensitive comparison instead of `ILIKE`, whose `%` and `_` wildcards
  could match unrelated titles.
- Requests to `/api/health` are no longer traced.
- `request_history` stores the validated `/api/media-info` parameters instead of the raw query string.

### Fixed

- TV episodes were answered with a cached movie that shares the series' TMDB id (for example
  `Slow.Horses.S06E06...` returned the movie "Flesh, TX"). TMDB numbers movies, series and episodes independently;
  cache lookups now always include the media type, and a cache hit of another media type is discarded.
- TV episode details were never fetched, so every episode of a series shared one cache row and later episodes
  received the first one's data. Episodes are now cached under their own TMDB id, specials (season 0) included.
- `/api/media-info` rejected season 0 as missing.
- Two identical requests at the same time no longer fail on the unique constraint; the second gets the row the first
  cached.
- A failure while recording OpenAI token usage no longer discards the model's answer, and reasoning tokens are
  recorded (they were always 0).
- Identified media without a release year (or another required value) is returned instead of failing with a 500.
- `is_valid_year` accepted years from 195; the range starts at 1888.
- The TMDB error log reports the 429 status when a connection error follows a rate-limit retry.
- guessit's fallback input no longer includes download-folder names such as `data`.
- Requests without client address information no longer fail.
- `run-image.sh` and `build-image.sh` are executable, and the readme's Windows build command tags the image the run
  command starts.

### Removed

- `requirements.txt`, gunicorn, and the unused `pipeline_builders.py`, `general_tasks.py` and
  `MediaInfoCache.update_cache`.

### Security

- `.dockerignore` is an allowlist, so `.env` and local settings files never reach the image.
- Error responses and `/api/statistics` no longer expose exception text (database, TMDB or OpenAI details).
  Statistics show the generic message for server errors recorded by 1.x as well; those rows stay unchanged in the
  database.

## [1.0.0]

Initial Release.

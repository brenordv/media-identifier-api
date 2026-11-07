# Media Identifier API

A RESTFUL API that identifies the media based on the filename. 

This project was created for educational purposes, showing how to:
1. Making different platforms work in tandem.
2. Applying caching to the system. (In this case, we don't need to worry about stale data, but still.)
3. How to use AI functions to get deterministic responses.

While I understand that an increasing number of poeple consider that 'if buying is not owning, pirating is not stealing,'
this API is not processing files, but working only with the filenames. You can create any scene-release filenames and 
test it as you like.
> TL;DR: Educational purposes, not condoning anything illegal. You do whatever you want at your own risk.

## Request flow
![Data flow chart](data-flow.png)

The happy path for identifying the media is:
- We try to guess data using GuessIT
- If we have the data cached, we return that;
- Otherwise, we use TMDB to identify it.
- If that fails, we use some AI Functions with OpenAI to identify the media.
- Then we call TMDB again to get details for the media;
- And again to get the external IDs (like IMDB id, etc.)
- Lastly, we cache this info, so we don't have to do the work twice.
- And return the data to the user.

We also log all requests coming in, the results, and if we use OpenAI, we log the tokens used.

## Endpoints

The application is built with FastAPI and exposes the GuessIt library's functionality through a RESTful API. It provides these endpoints:

- `/api/guess` - Analyzes a filename and returns structured information
- `/api/media-info` - Returns information about a media based on its title, etc.
- `/api/media-info/{media_id}` - Returns a cached media record by its id
- `/api/health` - Provides a health check to verify the API is functioning correctly
- `/api/statistics` - Returns statistics about requests made to the API

## Installation and Usage
### Environment variables
To use this, you must set a handful of environment variables. Copy `.env.example` to `.env` and fill it in:
```dotenv
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_USER=postgres
POSTGRES_PASSWORD=change-me
POSTGRES_DB=extended_media_info
TMDB_API_KEY=your-tmdb-api-read-access-token
OPENAI_API_KEY=your-openai-api-key
OPENAI_MODEL=gpt-4o-mini
OPENAI_ORGANIZATION=your-openai-organization-id
OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318
```

- `TMDB_API_KEY` is TMDB's "API Read Access Token" (it is sent as a bearer token).
- `OPENAI_MODEL` defaults to `gpt-4o-mini`, which works well here; other models work too.
- `POSTGRES_DB` defaults to `extended_media_info`.
- `OTEL_EXPORTER_OTLP_ENDPOINT` is required: logs and traces are exported to that OTLP/HTTP collector.
- Keep comments on their own lines and leave values unquoted: Docker's `--env-file` treats a `#` after a value,
  and any quotes, as part of the value.

### Local Installation

#### Prerequisites
- Python 3.12 or higher (`.python-version` selects 3.14 for development, the version the Docker image runs)
- [uv](https://docs.astral.sh/uv/)
- A PostgreSQL database

```bash
# Clone the repository
git clone https://github.com/brenordv/media-identifier-api.git
cd media-identifier-api

# Create the virtual environment and install the locked dependencies
uv sync

# Run the application
uv run python main.py
```

The API will be available at http://localhost:8000

### Database schema and migrations

The schema lives in versioned SQL files under `migrations/` (`NNNN_name.sql`). The API applies pending migrations
when it starts, so a fresh install needs nothing but an empty database the configured user can create tables in. To
apply them yourself, for example before a deploy:

```bash
uv run python -m src.database.migrate
```

Each file runs once, in its own transaction, and is recorded in the `schema_migrations` table with a checksum. Runs
take a PostgreSQL advisory lock, so several workers starting together are safe. An applied file must never be edited
(the checksum check stops the run); schema changes go in a new file with the next number.

### Tests and checks

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run pytest --cov
```

The unit tests need no database, TMDB, OpenAI or telemetry collector: they ignore `.env` and run with OpenTelemetry
disabled. The integration suite calls the live services configured in `.env` and writes to that database, so it only
runs on request:

```bash
MEDIA_IDENTIFIER_RUN_INTEGRATION=1 uv run pytest -m integration
```

### Using Docker
#### Building the Docker Image

```bash
# On Linux/macOS:
./build-image.sh

# On Windows (PowerShell):
docker build -t media-identifier-api:latest .
```

#### Running the Docker Container

```bash
# On Linux/macOS (reads .env next to the script, or the file in ENV_FILE):
./run-image.sh

# On Windows (PowerShell):
docker run -d --name media-identifier-api --env-file .env -p 10147:10147 --restart unless-stopped media-identifier-api:latest
```

The image contains no configuration (`.dockerignore` keeps `.env` out of the build), so the settings must be passed
when the container starts.

The API will be available at http://localhost:10147

## API Usage Examples
### Analyzing a Movie Filename

```
GET /api/guess?it=Shin%20Godzilla%20(2016)%201080p%20Hybrid%20Bluray%20REMUX%20AVC%20Dual%20DTS-HD%20MA%203.1
```

Response:
```json
{
  "title": "Shin Godzilla",
  "year": 2016,
  "screen_size": "1080p",
  "source": "Blu-ray",
  "other": "Hybrid, Remux",
  "video_codec": "H.264",
  "audio_channels": "3.1",
  "audio_codec": "DTS-HD"
}
```

### Analyzing a TV Show Filename

```
GET /api/guess?it=Rick.and.Morty.S07E10.Fear.No.Mort.1080p.HMAX.WEB-DL.DDP5.1.H.264-FLUX.mkv
```

Response:
```json
{
  "title": "Rick and Morty",
  "season": 7,
  "episode": 10,
  "episode_title": "Fear No Mort",
  "screen_size": "1080p",
  "streaming_service": "HBO Max",
  "source": "Web",
  "audio_codec": "Dolby Digital Plus",
  "audio_channels": "5.1",
  "video_codec": "H.264",
  "release_group": "FLUX",
  "container": "mkv"
}
```

### Health Check

```
GET /api/health
```

Response:
```json
{
  "message": "healthy"
}
```

### Statistics

```
GET /api/statistics?num_requests=5
```

Response:
```json
[
  {
    "id": "2577e39f-6ca8-4450-adae-f6395efc4862",
    "filename": "Death.Proof.2007.1080p.BluRay.x264-1920/1920-proof.rar",
    "requester_ip": "127.0.0.1",
    "result_status": 200,
    "result_media_id": "ed6822d6-e603-4dc9-8556-1a5289a950a7",
    "received_at": "2025-08-04T16:16:08.844097",
    "responded_at": "2025-08-04T16:16:42.564877",
    "elapsed_time": 1.02078,
    "error_message": null
  }
]
```

### Retrieving Media Information with Metadata

```
GET /api/media-info?media_type=movie&year=2024&title=Dune%3A%20Part%20Two
```

```
GET /api/media-info?media_type=tv&year=2023&title=Example%20Show&season=1&episode=2
```

> When using metadata for TV episodes, both `season` and `episode` parameters are required. The pipeline dynamically assembles the necessary identification steps based on the provided fields, so you can mix filename and metadata-driven lookups while keeping caching and enrichment consistent.

## More Examples

See the [example_requests.http](example_requests.http) file for more usage examples.

## Dependencies

This project relies on:
- [GuessIt](https://github.com/guessit-io/guessit) - The core library for parsing filenames
- [FastAPI](https://fastapi.tiangolo.com/) - Modern, fast web framework for building APIs
- [Uvicorn](https://www.uvicorn.org/) - ASGI server for running the application
- [Requests](https://requests.readthedocs.io/) - HTTP client for the TMDB API
- [raccoontools-db](https://pypi.org/project/raccoontools-db/) - PostgreSQL connection pool on top of [psycopg 3](https://www.psycopg.org/psycopg3/)
- [python-dotenv](https://pypi.org/project/python-dotenv/) - Library to handle `.env` files
- [simple-log-factory-ext-otel](https://pypi.org/project/simple-log-factory-ext-otel/) - OpenTelemetry logging and tracing on top of [simple-log-factory](https://pypi.org/project/simple-log-factory/) (Shameless plug: I made these. 😁)
- [openai](https://pypi.org/project/openai/) - Official OpenAI SDK.

## License

This project is licensed under the [GNU Lesser General Public License v3 (LGPLv3)](https://www.gnu.org/licenses/lgpl-3.0.html), the same license as the GuessIt library.

## Acknowledgements

This project is a simple wrapper around the excellent [GuessIt](https://github.com/guessit-io/guessit) library. 
All the hard work of parsing and analyzing filenames is done by GuessIt, and that project is absolutely awesome! So go 
check it out! :D 

We also heavily rely on the [TMDb API](https://developer.themoviedb.org/reference/intro/getting-started). 
It is hard to believe that their API have a free tier.

## Notes
- Used [gitignore](https://github.com/brenordv/rusted-toolbox/tree/master/crates/tool-gitignore) and [aiignore](https://github.com/brenordv/rusted-toolbox/tree/master/crates/tool-aiignore) tools to create the *ignore files.
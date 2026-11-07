# Media Identifier API

A RESTFUL API that identifies the media based on the filename. 

This project was created for educational purposes, showing how to:
1. Making different platforms work in tandem.
2. Applying caching to the system. (In this case, we don't need to worry about stale data, but still.)
3. How to use language models as a last resort, with structured answers that another service confirms.

While I understand that an increasing number of poeple consider that 'if buying is not owning, pirating is not stealing,'
this API is not processing files, but working only with the filenames. You can create any scene-release filenames and 
test it as you like.
> TL;DR: Educational purposes, not condoning anything illegal. You do whatever you want at your own risk.

## Request flow
The chart below shows the 1.x flow; the list describes the current one.

![Data flow chart](data-flow.png)

Identifying a file name goes like this:
- guessit reads the title, year, season and episode from the name.
- If that media is cached, the cached record is returned.
- The Nimble classifier (optional, see `MEDIA_IDENTIFIER_NIMBLE_URL`) decides whether the file is a movie, a TV
  release or neither. A confident "neither" (games, ROMs, images, documents) ends the request with 204. A confident movie or TV verdict
  sets the media type, even against guessit.
- When the media type is still uncertain, the name has no title, or a TV file has no season, OpenAI is asked once,
  with one structured call, what the name refers to.
- TMDB is searched for the title. When it finds nothing and OpenAI has not been asked yet, OpenAI suggests the title
  TMDB would list and TMDB is searched again.
- TMDB then provides the details and the external ids (IMDb and others), the record is cached, and it is returned.

A file nobody could identify ends with 204 and is recorded for review (see below). We log every request and its
outcome, and the tokens of every OpenAI call.

### Responses
- `200`: the media record.
- `204`: the file is not a movie or TV release, or nothing could identify it.
- `503`: a service the answer needs (TMDB, or OpenAI when it was the remaining option) is unavailable. Retry later.
- `500`: anything else went wrong.

### Reviewing files nobody could identify
`request_history.outcome` holds each request's verdict (`identified`, `not_media` or `unidentified`), and
`request_history.decided_by` the step that settled the media type (`guessit`, `nimble`, `openai`, or `request` for
`/api/media-info`). `/api/statistics` returns both. To list the files to look at:

```sql
SELECT received_at, filename
FROM request_history
WHERE outcome = 'unidentified' AND endpoint = '/api/guess'
ORDER BY received_at DESC;
```

`cached_media.used_nimble` marks the records whose media type Nimble set.

## Endpoints

The application is built with FastAPI and exposes the GuessIt library's functionality through a RESTful API. It provides these endpoints:

- `/api/guess` - Analyzes a filename and returns structured information
- `/api/media-info` - Returns information about a media based on its title, etc.
- `/api/media-info/{media_id}` - Returns a cached media record by its id
- `/api/health` - Provides a health check to verify the API is functioning correctly
- `/api/statistics` - Returns statistics about requests made to the API

## Installation and Usage
### Settings
The settings live in [Infisical](https://infisical.com/). The environment only holds what the API needs to reach
Infisical, plus two settings that are not secret. Copy `.env.example` to `.env` and fill it in:
```dotenv
INFISICAL_HOST=https://infisical.example.com
INFISICAL_ENV=dev
INFISICAL_MEDIA_IDENTIFIER_CLIENT_ID=your-machine-identity-client-id
INFISICAL_MEDIA_IDENTIFIER_CLIENT_SECRET=your-machine-identity-client-secret
INFISICAL_MEDIA_IDENTIFIER_PROJECT_ID=your-infisical-project-id
OPENAI_MODEL=gpt-4o-mini
OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318
```

- `INFISICAL_HOST` is the base URL of the Infisical server. A host without a scheme gets `https://`. Write `http://`
  only for a server without TLS: the client secret and every secret value then cross the network in clear text.
- `INFISICAL_ENV` is the Infisical environment the connection string and the Nimble URL are read from: `prod` in the
  deployed container, `dev` everywhere else. Without it, or with it blank, the API reads `dev`.
- `INFISICAL_MEDIA_IDENTIFIER_CLIENT_ID` and `INFISICAL_MEDIA_IDENTIFIER_CLIENT_SECRET` are the
  [Universal Auth](https://infisical.com/docs/documentation/platform/identities/universal-auth) credentials of a
  machine identity, and `INFISICAL_MEDIA_IDENTIFIER_PROJECT_ID` is the project holding the secrets. Give `dev` and
  `prod` each their own machine identity, with a project role that can only describe and read secrets at `/` in
  that environment and in `shared` (see below). A development `.env` then holds no credential that can read
  production's database or Nimble address, though it can read the OpenAI and TMDB settings in `shared`, and a
  production container that leaves out `INFISICAL_ENV` stops at startup with a permission error instead of reading
  `dev`.
- `OPENAI_MODEL` defaults to `gpt-4o-mini`; the model must support Structured Outputs.
- `OTEL_EXPORTER_OTLP_ENDPOINT` is required: logs and traces are exported to that OTLP/HTTP collector.
- Keep comments on their own lines and leave values unquoted: Docker's `--env-file` treats a `#` after a value,
  and any quotes, as part of the value.

The secrets sit at the root (`/`) of three Infisical environments. `shared` holds the OpenAI settings and the TMDB
key, which are the same everywhere. `prod` and `dev` hold the addresses: in `prod` they name containers on the
Docker network the API runs in, and in `dev` they use host names a development machine can reach.

| Secret                                        | Environment   | Required | What it holds                                                                          |
|-----------------------------------------------|---------------|----------|----------------------------------------------------------------------------------------|
| `MEDIA_IDENTIFIER_POSTGRES_CONNECTION_STRING` | `prod`, `dev` | yes      | The database connection string, including the database name (see below).              |
| `MEDIA_IDENTIFIER_TMDB_API_KEY`               | `shared`      | yes      | TMDB's "API Read Access Token" (sent as a bearer token).                               |
| `MEDIA_IDENTIFIER_OPENAI_API_KEY`             | `shared`      | no       | Without it the OpenAI fallback is off.                                                 |
| `MEDIA_IDENTIFIER_OPENAI_ORGANIZATION`        | `shared`      | no       | The OpenAI organization id.                                                            |
| `MEDIA_IDENTIFIER_NIMBLE_URL`                 | `prod`, `dev` | no       | Base URL of the Ollama server running the Nimble classifier; without it Nimble is off. |

- The API reads each secret from the environment the table gives it: the OpenAI settings and the TMDB key from
  `shared`, the other two from the environment in `INFISICAL_ENV`. Reads ignore Infisical secret imports, so a
  connection string or Nimble URL in `shared` is never used. A blank value counts as not set: a blank OpenAI key in
  `shared` turns the OpenAI fallback off in every environment, and a blank TMDB key stops the API in every
  environment.
- The connection string is a URI, `postgresql://user:password@host:5432/extended_media_info`, or `key=value` pairs,
  `host=host port=5432 user=user password='password' dbname=extended_media_info`. In a URI, percent-encode every
  character of the user name and password that is not a letter or digit, for example with
  `urllib.parse.quote(password, safe="")` (not `quote_plus`: it writes a space as `+`, which libpq reads as a literal
  `+`). In `key=value` form, put the value in single quotes and write a `'` or `\` inside it as `\'` or `\\`. A string
  without a database name, or one an unencoded `@`, `/` or `%` breaks, stops the API at startup with an error that
  does not repeat the string. Other unencoded characters can change the password libpq reads, so the login fails.
- The API has no authentication or rate limit, so set a spend limit on the OpenAI key's project.
- An invalid `MEDIA_IDENTIFIER_NIMBLE_URL` (not http or https, no host, or credentials in it) stops the API at
  startup.
- The API reads every setting when it starts and stops with an error naming the first required one that is missing.
  A secret changed in Infisical takes effect on the next start.

### Local Installation

#### Prerequisites
- Python 3.14 or higher, the version the Docker image runs (`uv sync` installs it when it is missing)
- [uv](https://docs.astral.sh/uv/)
- A PostgreSQL database
- An Infisical project with a Universal Auth machine identity (see Settings)

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

### Database user

Give the API a PostgreSQL role of its own instead of `postgres` or a role other applications share. The role below
can log in and owns the API's database objects, and has no other powers: it is not a superuser, cannot create
databases or roles, and cannot bypass row-level security. It has to own the tables because the API applies
migrations at startup, and `ALTER TABLE` is reserved for the owner.

Replace `change-me` with a generated password. `CREATE ROLE ... PASSWORD` sends the password in clear text and can
leave it in the server log or your client's history; in psql, create the role without the `PASSWORD` clause and run
`\password media_identifier` instead, which sends it already hashed. `\connect` is a psql command too: in another
client, run the statements after it in a session on `extended_media_info`.

For a new database, run as a superuser:

```sql
CREATE ROLE media_identifier WITH LOGIN PASSWORD 'change-me'
    NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;

-- The database belongs to the API, and no other role may connect to it.
CREATE DATABASE extended_media_info OWNER media_identifier;
REVOKE ALL ON DATABASE extended_media_info FROM PUBLIC;

\connect extended_media_info

-- Only the API may create objects in the public schema. PostgreSQL 15 and later already give the database owner
-- the public schema and keep other roles from creating objects in it; these two lines do the same on older versions.
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
GRANT USAGE, CREATE ON SCHEMA public TO media_identifier;
```

The first start then creates the `uuid-ossp` extension (a trusted extension, so the database owner may install it)
and the tables.

For a database that already holds the tables, created by another role, run as a superuser:

```sql
CREATE ROLE media_identifier WITH LOGIN PASSWORD 'change-me'
    NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
GRANT CONNECT ON DATABASE extended_media_info TO media_identifier;

\connect extended_media_info

-- Every start runs CREATE TABLE IF NOT EXISTS schema_migrations, which needs CREATE on the schema. Indexes change
-- owner with their table.
GRANT USAGE, CREATE ON SCHEMA public TO media_identifier;
ALTER TABLE IF EXISTS cached_media OWNER TO media_identifier;
ALTER TABLE IF EXISTS request_history OWNER TO media_identifier;
ALTER TABLE IF EXISTS openai_history OWNER TO media_identifier;
ALTER TABLE IF EXISTS schema_migrations OWNER TO media_identifier;
```

A 1.x deployment that still uses the database keeps working if it connects as a superuser such as `postgres`. One
that connects as another role stops starting once the tables change owner, because 1.x creates its tables and
indexes at startup and only the owner may create an index; move ownership after 2.0 replaces it, and until then
point 2.0's connection string at the role that owns the tables.

Then point `MEDIA_IDENTIFIER_POSTGRES_CONNECTION_STRING` at the role, for example
`postgresql://media_identifier:<percent-encoded password>@db-host:5432/extended_media_info`.

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

The unit tests need no Infisical, database, TMDB, OpenAI or telemetry collector: they ignore `.env`, serve every
secret from memory and run with OpenTelemetry disabled. The integration suite reads the live settings from Infisical
(with the bootstrap from `.env`), calls those services and writes to that database, so it only runs on request:

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

The image contains no configuration (`.dockerignore` keeps `.env` out of the build), so the Infisical bootstrap and
`OTEL_EXPORTER_OTLP_ENDPOINT` must be passed when the container starts, with `INFISICAL_ENV=prod`.

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
- [infisicalsdk](https://pypi.org/project/infisicalsdk/) - Official Infisical SDK, which reads the settings
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
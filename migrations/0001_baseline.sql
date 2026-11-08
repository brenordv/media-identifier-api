-- Tables and indexes of the 1.x schema. IF NOT EXISTS makes this a no-op on databases created by 1.x.
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

CREATE TABLE IF NOT EXISTS cached_media (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    searchable_reference TEXT NULL,
    tmdb_id INTEGER NOT NULL UNIQUE,
    tmdb_series_id INTEGER NULL,
    imdb_id TEXT NULL,
    tvdb_id INTEGER NULL,
    tvrage_id INTEGER NULL,
    wikidata_id TEXT NULL,
    facebook_id TEXT NULL,
    instagram_id TEXT NULL,
    twitter_id TEXT NULL,
    genres TEXT[] NULL,
    title TEXT NOT NULL,
    original_title TEXT NOT NULL,
    overview TEXT NULL,
    episode_title TEXT NULL,
    season INTEGER NULL,
    episode INTEGER NULL,
    original_language TEXT NULL,
    media_type TEXT NOT NULL,
    year INTEGER NOT NULL,
    tagline TEXT NULL,
    used_guessit BOOLEAN NOT NULL DEFAULT FALSE,
    used_tmdb BOOLEAN NOT NULL DEFAULT FALSE,
    used_openai BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    modified_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_cached_media_searchable_reference_ci ON cached_media (LOWER(searchable_reference));
CREATE INDEX IF NOT EXISTS idx_cached_media_title_ci ON cached_media (LOWER(title));
CREATE INDEX IF NOT EXISTS idx_cached_media_series_season_episode ON cached_media (tmdb_series_id, season, episode);
CREATE INDEX IF NOT EXISTS idx_cached_media_type_year ON cached_media (LOWER(media_type), year);

CREATE TABLE IF NOT EXISTS request_history (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    endpoint TEXT NOT NULL,
    filename TEXT NOT NULL,
    requester_ip TEXT NOT NULL,
    result_status INTEGER NULL,
    result_media_id UUID NULL,
    received_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    responded_at TIMESTAMP NULL,
    error_message TEXT NULL,
    elapsed_time INTERVAL GENERATED ALWAYS AS (responded_at - received_at) STORED
);

CREATE INDEX IF NOT EXISTS idx_request_history_received_at_desc ON request_history (received_at DESC);

CREATE TABLE IF NOT EXISTS openai_history (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    request_id UUID NOT NULL,
    input_tokens INTEGER NOT NULL,
    cached_tokens INTEGER NOT NULL,
    output_tokens INTEGER NOT NULL,
    reasoning_tokens INTEGER NOT NULL,
    total_tokens INTEGER NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_openai_history_request_id ON openai_history (request_id);

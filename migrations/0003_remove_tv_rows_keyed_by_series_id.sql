-- A TV row's tmdb_id is the episode's TMDB id; the series id belongs in tmdb_series_id.
-- Rows written with the series id as tmdb_id describe the wrong entity, so they are removed (the episodes are
-- identified again on their next request) and the CHECK keeps that shape out of the table.
LOCK TABLE cached_media IN ACCESS EXCLUSIVE MODE;

DELETE FROM cached_media
WHERE media_type = 'tv'
  AND tmdb_id = tmdb_series_id;

ALTER TABLE cached_media
    ADD CONSTRAINT ck_cached_media_tv_row_not_keyed_by_series
    CHECK (media_type <> 'tv' OR tmdb_id <> tmdb_series_id);

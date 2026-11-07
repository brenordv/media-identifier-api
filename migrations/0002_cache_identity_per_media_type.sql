-- TMDB numbers movies, series and episodes independently: movie 95480 and series 95480 are different titles.
-- A TMDB id therefore identifies a cached row only together with its media type.
DO $$
DECLARE
    unique_constraint record;
    dropped integer := 0;
BEGIN
    FOR unique_constraint IN
        SELECT con.conname
        FROM pg_constraint con
        JOIN pg_attribute att ON att.attrelid = con.conrelid AND att.attnum = con.conkey[1]
        WHERE con.conrelid = 'cached_media'::regclass
          AND con.contype = 'u'
          AND cardinality(con.conkey) = 1
          AND att.attname = 'tmdb_id'
    LOOP
        EXECUTE format('ALTER TABLE cached_media DROP CONSTRAINT %I', unique_constraint.conname);
        dropped := dropped + 1;
    END LOOP;

    IF dropped <> 1 THEN
        RAISE EXCEPTION 'expected exactly one UNIQUE (tmdb_id) constraint on cached_media, found %', dropped;
    END IF;
END $$;

ALTER TABLE cached_media
    ADD CONSTRAINT uq_cached_media_tmdb_id_media_type UNIQUE (tmdb_id, media_type);

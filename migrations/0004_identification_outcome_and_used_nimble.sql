-- used_nimble marks cached records whose media type the Nimble classifier set.
-- request_history.outcome records the verdict of each identification request (outcome = 'unidentified' is the list
-- of files nobody could identify), and decided_by records which step settled the media type or the not_media verdict.
-- The short lock timeout makes this file give up quickly, instead of holding cached_media while it waits for
-- request_history behind another client's transaction.
SET LOCAL lock_timeout = '5s';

ALTER TABLE cached_media ADD COLUMN used_nimble BOOLEAN NOT NULL DEFAULT FALSE;

ALTER TABLE request_history
    ADD COLUMN outcome TEXT,
    ADD COLUMN decided_by TEXT;

ALTER TABLE request_history
    ADD CONSTRAINT ck_request_history_outcome
        CHECK (outcome IN ('identified', 'not_media', 'unidentified')),
    ADD CONSTRAINT ck_request_history_decided_by
        CHECK (decided_by IN ('guessit', 'nimble', 'openai', 'request'));

COMMENT ON COLUMN request_history.outcome IS
    'identified, not_media or unidentified; NULL when no verdict was reached or the row predates 2.0.0';
COMMENT ON COLUMN request_history.decided_by IS
    'step that settled the media type or the not_media verdict; NULL for unidentified, failed or pre-2.0.0 requests';

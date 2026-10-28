-- Cache the exact serialized snapshot payload for efficient verified downloads.
-- Existing snapshots are backfilled lazily on their first manifest/chunk request.
ALTER TABLE snapshots
    ADD COLUMN IF NOT EXISTS raw_payload BYTEA;

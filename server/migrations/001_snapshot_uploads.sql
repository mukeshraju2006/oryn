-- Apply once to the production PostgreSQL database before deploying the
-- chunked-upload backend. Existing snapshots are unchanged.
CREATE TABLE IF NOT EXISTS snapshot_uploads (
    id VARCHAR(36) PRIMARY KEY,
    workspace_id BIGINT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    chunk_count INTEGER NOT NULL CHECK (chunk_count > 0),
    total_bytes INTEGER NOT NULL CHECK (total_bytes > 0),
    sha256 VARCHAR(64) NOT NULL,
    snapshot_id BIGINT REFERENCES snapshots(id) ON DELETE SET NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
ALTER TABLE snapshot_uploads
    ADD COLUMN IF NOT EXISTS snapshot_id INTEGER REFERENCES snapshots(id) ON DELETE SET NULL;
CREATE INDEX IF NOT EXISTS ix_snapshot_uploads_workspace_id ON snapshot_uploads(workspace_id);
CREATE INDEX IF NOT EXISTS ix_snapshot_uploads_user_id ON snapshot_uploads(user_id);

CREATE TABLE IF NOT EXISTS snapshot_upload_chunks (
    id SERIAL PRIMARY KEY,
    upload_id VARCHAR(36) NOT NULL REFERENCES snapshot_uploads(id) ON DELETE CASCADE,
    chunk_index INTEGER NOT NULL CHECK (chunk_index >= 0),
    sha256 VARCHAR(64) NOT NULL,
    data BYTEA NOT NULL,
    CONSTRAINT uq_snapshot_upload_chunk UNIQUE (upload_id, chunk_index)
);
CREATE INDEX IF NOT EXISTS ix_snapshot_upload_chunks_upload_id ON snapshot_upload_chunks(upload_id);

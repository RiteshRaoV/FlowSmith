CREATE TABLE IF NOT EXISTS fs_flows (
    id          TEXT NOT NULL PRIMARY KEY,
    name        TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'RUNNING',
    input_data  TEXT NOT NULL,
    output_data TEXT,
    error       TEXT,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_fs_flows_status ON fs_flows (status);
CREATE INDEX IF NOT EXISTS idx_fs_flows_name   ON fs_flows (name);

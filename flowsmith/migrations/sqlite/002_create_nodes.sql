CREATE TABLE IF NOT EXISTS fs_nodes (
    id            TEXT    NOT NULL PRIMARY KEY,
    flow_id       TEXT    NOT NULL,
    step_name     TEXT    NOT NULL,
    status        TEXT    NOT NULL DEFAULT 'RUNNING',
    input_data    TEXT,
    output_data   TEXT,
    error         TEXT,
    attempt_count INTEGER NOT NULL DEFAULT 1,
    started_at    TEXT,
    ended_at      TEXT,

    FOREIGN KEY (flow_id) REFERENCES fs_flows(id) ON DELETE CASCADE,
    UNIQUE (flow_id, step_name)
);

CREATE INDEX IF NOT EXISTS idx_fs_nodes_flow_id ON fs_nodes (flow_id);
CREATE INDEX IF NOT EXISTS idx_fs_nodes_status  ON fs_nodes (status);

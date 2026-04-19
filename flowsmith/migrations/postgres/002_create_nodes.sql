CREATE TABLE IF NOT EXISTS fs_nodes (
    id            TEXT        PRIMARY KEY DEFAULT gen_random_uuid()::text,
    flow_id       TEXT        NOT NULL REFERENCES fs_flows(id) ON DELETE CASCADE,
    step_name     TEXT        NOT NULL,
    status        TEXT        NOT NULL DEFAULT 'RUNNING',  -- RUNNING | FAILED | COMPLETED
    input_data    JSONB,
    output_data   JSONB,
    error         TEXT,
    attempt_count INT         NOT NULL DEFAULT 1,
    started_at    TIMESTAMPTZ,
    ended_at      TIMESTAMPTZ,

    -- Ensures only one node record per (flow, step) pair
    CONSTRAINT uq_fs_nodes_flow_step UNIQUE (flow_id, step_name)
);

CREATE INDEX IF NOT EXISTS idx_fs_nodes_flow_id    ON fs_nodes (flow_id);
CREATE INDEX IF NOT EXISTS idx_fs_nodes_status     ON fs_nodes (status);

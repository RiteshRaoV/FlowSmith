CREATE TABLE IF NOT EXISTS ff_nodes (
    id            TEXT        PRIMARY KEY DEFAULT gen_random_uuid()::text,
    flow_id       TEXT        NOT NULL REFERENCES ff_flows(id) ON DELETE CASCADE,
    step_name     TEXT        NOT NULL,
    status        TEXT        NOT NULL DEFAULT 'RUNNING',  -- RUNNING | FAILED | COMPLETED
    input_data    JSONB,
    output_data   JSONB,
    error         TEXT,
    attempt_count INT         NOT NULL DEFAULT 1,
    started_at    TIMESTAMPTZ,
    ended_at      TIMESTAMPTZ,

    -- Ensures only one node record per (flow, step) pair
    CONSTRAINT uq_ff_nodes_flow_step UNIQUE (flow_id, step_name)
);

CREATE INDEX IF NOT EXISTS idx_ff_nodes_flow_id    ON ff_nodes (flow_id);
CREATE INDEX IF NOT EXISTS idx_ff_nodes_status     ON ff_nodes (status);

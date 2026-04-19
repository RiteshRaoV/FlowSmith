CREATE TABLE IF NOT EXISTS fs_flows (
    id           TEXT        PRIMARY KEY,          -- caller-supplied tracking_id
    name         TEXT        NOT NULL,             -- workflow name
    status       TEXT        NOT NULL DEFAULT 'RUNNING',  -- RUNNING | FAILED | COMPLETED
    input_data   JSONB       NOT NULL DEFAULT '{}',
    output_data  JSONB,
    error        TEXT,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_fs_flows_status ON fs_flows (status);
CREATE INDEX IF NOT EXISTS idx_fs_flows_name   ON fs_flows (name);

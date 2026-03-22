CREATE TABLE IF NOT EXISTS ff_flows (
    id           TEXT        PRIMARY KEY,          -- caller-supplied tracking_id
    name         TEXT        NOT NULL,             -- workflow name
    status       TEXT        NOT NULL DEFAULT 'RUNNING',  -- RUNNING | FAILED | COMPLETED
    input_data   JSONB       NOT NULL DEFAULT '{}',
    output_data  JSONB,
    error        TEXT,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_ff_flows_status ON ff_flows (status);
CREATE INDEX IF NOT EXISTS idx_ff_flows_name   ON ff_flows (name);

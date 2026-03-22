CREATE TABLE IF NOT EXISTS ff_flows (
    id          VARCHAR(255)    NOT NULL PRIMARY KEY,
    name        VARCHAR(255)    NOT NULL,
    status      VARCHAR(50)     NOT NULL DEFAULT 'RUNNING',
    input_data  JSON            NOT NULL,
    output_data JSON,
    error       TEXT,
    created_at  DATETIME(6)     NOT NULL DEFAULT NOW(6),
    updated_at  DATETIME(6)     NOT NULL DEFAULT NOW(6) ON UPDATE NOW(6)
);

CREATE INDEX IF NOT EXISTS idx_ff_flows_status ON ff_flows (status);
CREATE INDEX IF NOT EXISTS idx_ff_flows_name   ON ff_flows (name);
